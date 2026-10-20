import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.auth import get_current_user, AuthenticatedUser
from app.core.audit import audit_service, PROHIBITED_DETAIL_KEYS
from app.core.dedup import profile_read_dedup, ProfileReadDedupService
from app.core.middleware import get_request_id
from app.core.security import hash_phone
from app.core.rate_limit import rate_limiter
from tests.test_patient_auth import MockSupabaseClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_dedup_and_test_state():
    """Reset dedup cache before each test."""
    profile_read_dedup.reset_for_tests()


# -----------------------------------------------------------------------------
# 1. Request-ID Middleware & Header Propagation Tests
# -----------------------------------------------------------------------------
def test_request_id_middleware_generates_uuid_when_missing():
    """When X-Request-ID header is missing, middleware generates a valid UUIDv4."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    generated_id = response.headers["X-Request-ID"]
    # Verify it parses as a valid UUID
    parsed = uuid.UUID(generated_id)
    assert parsed.version == 4


def test_request_id_middleware_preserves_valid_incoming_id():
    """When a valid UUID X-Request-ID header is supplied, middleware preserves it."""
    client_request_id = str(uuid4())
    response = client.get("/api/v1/health", headers={"X-Request-ID": client_request_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == client_request_id


def test_request_id_middleware_replaces_malformed_id():
    """When a malformed X-Request-ID header is supplied (e.g. SQL injection or arbitrary text),
    middleware discards it and generates a fresh UUIDv4."""
    malformed_id = "malicious'-- DROP TABLE audit_logs;"
    response = client.get("/api/v1/health", headers={"X-Request-ID": malformed_id})
    assert response.status_code == 200
    returned_id = response.headers.get("X-Request-ID")
    assert returned_id != malformed_id
    parsed = uuid.UUID(returned_id)
    assert parsed.version == 4



# -----------------------------------------------------------------------------
# 2. Audit Detail Sanitization Tests
# -----------------------------------------------------------------------------
def test_audit_sanitizer_redacts_prohibited_sensitive_keys():
    """Sensitive keys (passwords, OTPs, raw tokens, Aadhaar) must be redacted."""
    raw_details = {
        "password": "SuperSecretPassword123!",
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "otp": "948214",
        "aadhaar": "1234-5678-9012",
        "secret": "top-secret-val",
        "patient_id": "MED-2026-ABC123",
        "reason": "profile_access",
    }
    clean = audit_service.sanitize_details(raw_details, request_id="req-123")

    # Prohibited keys redacted
    assert clean["password"] == "[REDACTED]"
    assert clean["token"] == "[REDACTED]"
    assert clean["otp"] == "[REDACTED]"
    assert clean["aadhaar"] == "[REDACTED]"
    assert clean["secret"] == "[REDACTED]"

    # Non-sensitive keys and request_id preserved intact
    assert clean["patient_id"] == "MED-2026-ABC123"
    assert clean["reason"] == "profile_access"
    assert clean["request_id"] == "req-123"


# -----------------------------------------------------------------------------
# 3. 15-Minute Profile-Read Deduplication Tests
# -----------------------------------------------------------------------------
def test_profile_read_deduplication_five_rapid_reads(monkeypatch):
    """5 rapid GET /api/v1/patients/me calls by the same user produce exactly 1 audit log."""
    mock_db = MockSupabaseClient()
    user_id = uuid4()
    profile_id = str(uuid4())

    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "patient_id": "MED-2026-DEDUP1",
        "user_id": str(user_id),
        "full_name": "Dedup Test Patient",
        "date_of_birth": "1991-03-14",
        "gender": "female",
        "verification_status": "phone_verified",
        "created_at": "2026-10-19T12:00:00Z",
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=user_id, phone="+919876543210")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        # Fire 5 rapid GET /me requests
        for _ in range(5):
            res = client.get("/api/v1/patients/me")
            assert res.status_code == 200

        # Verify audit logs table has EXACTLY 1 patient_profile_read entry
        audit_records = [
            r for r in mock_db.table("audit_logs").data
            if r.get("action") == "patient_profile_read"
        ]
        assert len(audit_records) == 1
        assert audit_records[0]["actor_user_id"] == str(user_id)
        assert audit_records[0]["entity_id"] == profile_id
        assert "request_id" in audit_records[0]["details"]

        # If cache resets (simulating 15-minute window expiry), next read emits 2nd event
        profile_read_dedup.reset_for_tests()
        res = client.get("/api/v1/patients/me")
        assert res.status_code == 200

        audit_records_after = [
            r for r in mock_db.table("audit_logs").data
            if r.get("action") == "patient_profile_read"
        ]
        assert len(audit_records_after) == 2
    finally:
        app.dependency_overrides.clear()


def test_concurrent_profile_reads_thread_safety():
    """Concurrent threads checking should_log produce thread-safe deduplication."""
    dedup = ProfileReadDedupService(window_seconds=900)
    user_id = str(uuid4())

    results = []

    def check_log():
        should = dedup.should_log(user_id)
        if should:
            dedup.mark_logged(user_id)
            results.append(True)
        else:
            results.append(False)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_log) for _ in range(10)]
        for f in futures:
            f.result()

    # In a rapid burst, exactly 1 thread wins the write check and others are deduplicated
    assert results.count(True) == 1
    assert results.count(False) == 9


def test_dedup_cache_fails_open_to_logging(monkeypatch):
    """If the deduplication cache encounters an unexpected error, it fails open to logging."""
    dedup = ProfileReadDedupService(window_seconds=900)
    # Simulate an error inside the lock
    monkeypatch.setattr(dedup, "_cache", None)

    # should_log must fail open to True
    assert dedup.should_log("some-user") is True


# -----------------------------------------------------------------------------
# 4. Failed Recovery Challenge Auditing Tests
# -----------------------------------------------------------------------------
def test_failed_recovery_challenge_audited_without_guessed_values(monkeypatch):
    """When a recovery challenge fails due to mismatched DOB, an audit event is durably recorded,
    and guessed demographic values (DOB) are NOT leaked into audit details."""
    mock_db = MockSupabaseClient()
    owner_user_id = uuid4()
    attacker_user_id = uuid4()
    target_pid = "MED-2026-CHALLENGE1"

    mock_db.table("patient_profiles").data.append({
        "id": str(uuid4()),
        "patient_id": target_pid,
        "user_id": str(owner_user_id),
        "phone_hash": "dummy-hash",
        "full_name": "Target Patient",
        "date_of_birth": "1985-05-20",  # Real DOB
        "gender": "male",
        "verification_status": "phone_verified",
        "created_at": "2026-10-19T12:00:00Z",
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    attacker_user = AuthenticatedUser(id=attacker_user_id, phone="+917000000000")
    app.dependency_overrides[get_current_user] = lambda: attacker_user

    guessed_dob = "1999-12-31"  # Attacker guess
    req_uuid = str(uuid4())

    try:
        payload = {
            "target_patient_id": target_pid,
            "challenge_date_of_birth": guessed_dob,
        }
        response = client.post(
            "/api/v1/patients/recovery/initiate",
            json=payload,
            headers={"X-Request-ID": req_uuid},
        )
        assert response.status_code == 400

        # Assert audit record exists
        failed_audits = [
            r for r in mock_db.table("audit_logs").data
            if r.get("action") == "patient_recovery_challenge_failed"
        ]
        assert len(failed_audits) == 1
        record = failed_audits[0]
        assert record["actor_user_id"] == str(attacker_user_id)
        assert record["details"]["target_patient_id"] == target_pid
        assert record["details"]["reason"] == "demographic_mismatch"
        assert record["details"]["request_id"] == req_uuid

        # CRITICAL SECURITY ASSERTION: Guessed DOB must NEVER appear in audit details!
        details_str = str(record["details"])
        assert guessed_dob not in details_str
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 5. Unauthorized Recovery Completion Auditing Tests
# -----------------------------------------------------------------------------
def test_unauthorized_recovery_completion_attempt_audited(monkeypatch):
    """When /recovery/verify is called on an unapproved recovery request, an audit log is
    recorded and HTTP 403 Forbidden is returned."""
    mock_db = MockSupabaseClient()
    attacker_user_id = uuid4()
    recovery_req_id = str(uuid4())
    req_uuid = str(uuid4())

    mock_db.table("patient_recovery_requests").data.append({
        "id": recovery_req_id,
        "patient_profile_id": str(uuid4()),
        "status": "pending_institutional_approval",  # Unapproved
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    attacker_user = AuthenticatedUser(id=attacker_user_id, phone="+917000000000")
    app.dependency_overrides[get_current_user] = lambda: attacker_user

    try:
        response = client.post(
            "/api/v1/patients/recovery/verify",
            json={"recovery_request_id": recovery_req_id},
            headers={"X-Request-ID": req_uuid},
        )
        assert response.status_code == 403

        # Assert audit log exists
        unauth_audits = [
            r for r in mock_db.table("audit_logs").data
            if r.get("action") == "patient_recovery_unauthorized_completion_attempt"
        ]
        assert len(unauth_audits) == 1
        record = unauth_audits[0]
        assert record["actor_user_id"] == str(attacker_user_id)
        assert record["entity_id"] == recovery_req_id
        assert record["details"]["current_status"] == "pending_institutional_approval"
        assert record["details"]["request_id"] == req_uuid
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 6. Atomic Mutation Request-ID Propagation Tests
# -----------------------------------------------------------------------------
def test_profile_creation_and_update_propagates_request_id_to_audit(monkeypatch):
    """Atomic profile registration and update bind the HTTP request ID into the audit record."""
    mock_db = MockSupabaseClient()
    user_id = uuid4()
    req_id_1 = str(uuid4())
    req_id_2 = str(uuid4())

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=user_id, phone="+919111111111")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        # 1. Create profile
        create_payload = {
            "full_name": "Atomic Audit Patient",
            "date_of_birth": "1994-06-15",
            "gender": "male",
            "blood_group": "O+",
        }
        res1 = client.post(
            "/api/v1/patients/profile",
            json=create_payload,
            headers={"X-Request-ID": req_id_1},
        )
        assert res1.status_code == 201
        assert res1.headers.get("X-Request-ID") == req_id_1

        created_audits = [
            r for r in mock_db.table("audit_logs").data
            if r.get("action") == "patient_profile_created"
        ]
        assert len(created_audits) == 1
        assert created_audits[0]["details"]["request_id"] == req_id_1

        # 2. Update profile
        update_payload = {
            "emergency_contact_phone": "+919999900000",
        }
        res2 = client.patch(
            "/api/v1/patients/me",
            json=update_payload,
            headers={"X-Request-ID": req_id_2},
        )
        assert res2.status_code == 200
        assert res2.headers.get("X-Request-ID") == req_id_2

        updated_audits = [
            r for r in mock_db.table("audit_logs").data
            if r.get("action") == "patient_profile_updated"
        ]
        assert len(updated_audits) == 1
        assert updated_audits[0]["details"]["request_id"] == req_id_2
        assert "emergency_contact_phone" in updated_audits[0]["details"]["updated_fields"]
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 7. Registration and Recovery Phone Binding Regression Tests
# -----------------------------------------------------------------------------
def test_registration_requires_verified_phone_on_account(monkeypatch):
    """An authenticated account without a verified phone number cannot register a patient profile."""
    mock_db = MockSupabaseClient()
    user_id = uuid4()

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    # User authenticated via email-only or unverified phone
    mock_user = AuthenticatedUser(id=user_id, phone=None)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "full_name": "No Phone Patient",
            "date_of_birth": "1995-01-01",
            "gender": "female",
        }
        res = client.post("/api/v1/patients/profile", json=payload)
        assert res.status_code == 400
        assert "verified phone number" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_registration_normalizes_phone_consistently(monkeypatch):
    """Registration normalizes formatted phone numbers (spaces, dashes) to clean E.164 and valid hash."""
    mock_db = MockSupabaseClient()
    user_id = uuid4()

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    # Phone with formatting
    mock_user = AuthenticatedUser(id=user_id, phone="+91 98765 43210")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "full_name": "Formatted Phone Patient",
            "date_of_birth": "1993-05-12",
            "gender": "male",
        }
        res = client.post("/api/v1/patients/profile", json=payload)
        assert res.status_code == 201

        # Profile in mock DB must have clean normalized E.164 hash
        created = mock_db.table("patient_profiles").data[0]
        assert created["phone_hash"] == hash_phone("+91 98765 43210")
    finally:
        app.dependency_overrides.clear()


def test_recovery_verify_requires_verified_phone_on_caller(monkeypatch):
    """Calling /recovery/verify without a verified phone on the caller account returns HTTP 400."""
    mock_db = MockSupabaseClient()
    caller_id = uuid4()
    req_id = str(uuid4())

    mock_db.table("patient_recovery_requests").data.append({
        "id": req_id,
        "patient_profile_id": str(uuid4()),
        "status": "approved_by_staff",
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    # Caller has no verified phone
    mock_user = AuthenticatedUser(id=caller_id, phone=None)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        res = client.post("/api/v1/patients/recovery/verify", json={"recovery_request_id": req_id})
        assert res.status_code == 400
        assert "verified phone number" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_registration_rejects_unconfirmed_phone_in_database(monkeypatch):
    """Calling /profile when database rejects unconfirmed phone returns HTTP 403."""
    mock_db = MockSupabaseClient()
    user_id = uuid4()

    def mock_rpc(func_name, params):
        class MockRPC:
            def execute(self):
                raise Exception("Authenticated user phone number is unconfirmed or missing in authentication engine.")
        return MockRPC()

    mock_db.rpc = mock_rpc
    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=user_id, phone="+919876543210")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "full_name": "Unconfirmed User",
            "date_of_birth": "1990-01-01",
            "gender": "male",
        }
        res = client.post("/api/v1/patients/profile", json=payload)
        assert res.status_code == 403
        assert "confirmed phone number" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_invalid_jwt_emits_structured_log(monkeypatch, caplog):
    """Invalid JWT must emit structured log with event='auth_token_invalid' and outcome='denied'."""
    test_secret = "super-secret-test-key-32-characters-minimum!"
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: None)

    with caplog.at_level(logging.WARNING, logger="security.auth"):
        response = client.get(
            "/api/v1/patients/me",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )
        assert response.status_code == 401
        
        auth_logs = [r for r in caplog.records if r.name == "security.auth"]
        assert len(auth_logs) > 0
        matching = [r for r in auth_logs if getattr(r, "event", None) == "auth_token_invalid"]
        assert len(matching) > 0
        assert getattr(matching[0], "outcome", None) == "denied"


def test_expired_jwt_emits_structured_log(monkeypatch, caplog):
    """Expired JWT must emit structured log with event='auth_token_expired' and outcome='denied'."""
    test_secret = "super-secret-test-key-32-characters-minimum!"
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: None)

    expired_payload = {
        "sub": str(uuid4()),
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
    }
    expired_token = jwt.encode(expired_payload, test_secret, algorithm="HS256")

    with caplog.at_level(logging.WARNING, logger="security.auth"):
        response = client.get(
            "/api/v1/patients/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

        auth_logs = [r for r in caplog.records if r.name == "security.auth"]
        assert len(auth_logs) > 0
        matching = [r for r in auth_logs if getattr(r, "event", None) == "auth_token_expired"]
        assert len(matching) > 0
        assert getattr(matching[0], "outcome", None) == "denied"


def test_rate_limit_emits_structured_log(caplog):
    """Exceeding rate limit emits structured log with event='rate_limit_exceeded'."""
    rate_limiter.reset_for_tests()
    with caplog.at_level(logging.WARNING, logger="security.rate_limit"):
        for _ in range(5):
            rate_limiter.check("test_event", "127.0.0.1", max_requests=5, window_seconds=60)

        with pytest.raises(Exception):
            rate_limiter.check("test_event", "127.0.0.1", max_requests=5, window_seconds=60)

        rl_logs = [r for r in caplog.records if r.name == "security.rate_limit"]
        assert len(rl_logs) > 0
        matching = [r for r in rl_logs if getattr(r, "event", None) == "rate_limit_exceeded"]
        assert len(matching) > 0
        assert getattr(matching[0], "rate_limit_key", None) == "test_event"
        assert getattr(matching[0], "outcome", None) == "denied"
    rate_limiter.reset_for_tests()


