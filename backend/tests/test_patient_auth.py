import time
from datetime import date, datetime, timezone, timedelta
from uuid import uuid4
import jwt
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import generate_patient_id, normalize_phone, hash_phone, mask_phone
from app.core.auth import get_current_user, AuthenticatedUser
from app.core.config import settings
from app.core.rate_limit import rate_limiter

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset rate limiter state before each test."""
    rate_limiter.reset_for_tests()


# -----------------------------------------------------------------------------
# 1. Security & Identity Utility Tests
# -----------------------------------------------------------------------------
def test_generate_patient_id_format():
    """Verify Patient ID matches format MED-YYYY-XXXXXX with collision resistance."""
    pid1 = generate_patient_id(2026)
    pid2 = generate_patient_id(2026)

    assert pid1.startswith("MED-2026-")
    assert len(pid1) == 15  # "MED-2026-" (9) + 6 chars = 15
    assert pid1 != pid2

    # Verify no ambiguous characters (0, O, 1, I)
    ambiguous = {"0", "O", "1", "I"}
    random_part = pid1.split("-")[2]
    assert not any(c in ambiguous for c in random_part)


def test_phone_normalization_and_hashing():
    """Verify phone numbers in various formats produce identical deduplication hashes."""
    raw1 = "+91 98765 43210"
    raw2 = "+91-98765-43210"
    raw3 = "9876543210"

    norm1 = normalize_phone(raw1)
    norm2 = normalize_phone(raw2)
    norm3 = normalize_phone(raw3)

    assert norm1 == "+919876543210"
    assert norm2 == "+919876543210"
    assert norm3 == "+919876543210"

    hash1 = hash_phone(raw1)
    hash2 = hash_phone(raw2)
    hash3 = hash_phone(raw3)

    assert hash1 == hash2 == hash3
    assert len(hash1) == 64  # SHA-256 hex string


def test_phone_masking():
    """Verify phone masking preserves country prefix and last digits for safe display."""
    masked = mask_phone("+919876543210")
    assert masked.startswith("+91")
    assert masked.endswith("3210")
    assert "*" in masked


# -----------------------------------------------------------------------------
# 2. Token Cryptographic Claims & Auth Guard Tests
# -----------------------------------------------------------------------------
def test_unauthenticated_access_denied():
    """Attempting to access /api/v1/patients/me without Bearer token must return 401."""
    response = client.get("/api/v1/patients/me")
    assert response.status_code == 401
    assert "detail" in response.json()


def test_malformed_token_rejected():
    """Malformed token string must return 401."""
    response = client.get(
        "/api/v1/patients/me",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"},
    )
    assert response.status_code in [401, 503]


def test_expired_token_rejected(monkeypatch):
    """JWT with past expiration timestamp (exp) must be rejected with 401."""
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

    response = client.get(
        "/api/v1/patients/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json().get("detail", "").lower()


def test_invalid_audience_token_rejected(monkeypatch):
    """JWT with invalid audience claim (e.g. 'wrong_audience') must be rejected with 401."""
    test_secret = "super-secret-test-key-32-characters-minimum!"
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: None)

    invalid_aud_payload = {
        "sub": str(uuid4()),
        "aud": "wrong_audience",
        "role": "authenticated",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    bad_token = jwt.encode(invalid_aud_payload, test_secret, algorithm="HS256")

    response = client.get(
        "/api/v1/patients/me",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert response.status_code == 401
    assert "audience" in response.json().get("detail", "").lower()


def test_missing_environment_configuration_fails_safely(monkeypatch):
    """When DB credentials are unconfigured and token verification cannot run, fails with 503."""
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: None)
    monkeypatch.setattr("app.core.auth.is_db_configured", lambda: False)

    response = client.get(
        "/api/v1/patients/me",
        headers={"Authorization": "Bearer some-token"},
    )
    assert response.status_code == 503
    assert "unconfigured" in response.json()["detail"].lower()


# -----------------------------------------------------------------------------
# 3. Database Mocking & Multi-Tenant Isolation Tests
# -----------------------------------------------------------------------------
class MockSupabaseTable:
    def __init__(self, data=None):
        self.data = data or []
        self._filter_field = None
        self._filter_val = None

    def select(self, fields="*"):
        return self

    def eq(self, field, value):
        self._filter_field = field
        self._filter_val = value
        return self

    def insert(self, record):
        inserted = dict(record)
        if "id" not in inserted:
            inserted["id"] = str(uuid4())
        if "created_at" not in inserted:
            inserted["created_at"] = "2026-10-19T12:00:00Z"
        self.data.append(inserted)
        return self

    def update(self, updates):
        for item in self.data:
            if self._filter_field and str(item.get(self._filter_field)) == str(self._filter_val):
                item.update(updates)
        return self

    def execute(self):
        filtered = self.data
        if self._filter_field and self._filter_val:
            filtered = [
                d for d in self.data
                if str(d.get(self._filter_field)) == str(self._filter_val)
            ]
        class Result:
            pass
        res = Result()
        res.data = filtered
        return res


class MockSupabaseClient:
    def __init__(self):
        self.tables = {
            "users": MockSupabaseTable(),
            "patient_profiles": MockSupabaseTable(),
            "patient_recovery_requests": MockSupabaseTable(),
            "audit_logs": MockSupabaseTable(),
        }

    def table(self, table_name):
        if table_name not in self.tables:
            self.tables[table_name] = MockSupabaseTable()
        return self.tables[table_name]


def test_cross_patient_isolation(monkeypatch):
    """Patient A cannot retrieve or modify Patient B's profile.

    Endpoint strictly fetches records where user_id == current_user.id.
    """
    mock_db = MockSupabaseClient()
    patient_a_id = uuid4()
    patient_b_id = uuid4()

    mock_db.table("patient_profiles").data.append({
        "id": str(uuid4()),
        "patient_id": "MED-2026-AAA111",
        "user_id": str(patient_a_id),
        "full_name": "Patient Alpha",
        "date_of_birth": "1990-01-01",
        "gender": "female",
        "verification_status": "phone_verified",
        "created_at": "2026-10-19T12:00:00Z",
    })

    mock_db.table("patient_profiles").data.append({
        "id": str(uuid4()),
        "patient_id": "MED-2026-BBB222",
        "user_id": str(patient_b_id),
        "full_name": "Patient Bravo",
        "date_of_birth": "1988-08-08",
        "gender": "male",
        "verification_status": "phone_verified",
        "created_at": "2026-10-19T12:00:00Z",
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    # Session is authenticated as Patient A
    mock_user_a = AuthenticatedUser(id=patient_a_id, phone="+919876543210")
    app.dependency_overrides[get_current_user] = lambda: mock_user_a

    try:
        response = client.get("/api/v1/patients/me")
        assert response.status_code == 200
        data = response.json()
        assert data["patient_id"] == "MED-2026-AAA111"
        assert data["full_name"] == "Patient Alpha"
        # Must never return Patient B's info
        assert data["patient_id"] != "MED-2026-BBB222"
    finally:
        app.dependency_overrides.clear()


def test_idempotent_registration_prevents_duplicate_profile(monkeypatch):
    """If authenticated user already has a profile, create_patient_profile returns it idempotently."""
    mock_db = MockSupabaseClient()
    user_id = uuid4()
    patient_id = "MED-2026-TEST01"

    mock_db.table("patient_profiles").data.append({
        "id": str(uuid4()),
        "patient_id": patient_id,
        "user_id": str(user_id),
        "full_name": "Test Patient",
        "date_of_birth": "1990-01-01",
        "gender": "female",
        "verification_status": "phone_verified",
        "created_at": "2026-10-19T12:00:00Z",
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=user_id, phone="+919876543210")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "full_name": "Test Patient",
            "date_of_birth": "1990-01-01",
            "gender": "female",
        }
        response = client.post("/api/v1/patients/profile", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["patient_id"] == patient_id
        assert len(mock_db.table("patient_profiles").data) == 1
    finally:
        app.dependency_overrides.clear()


def test_registration_detects_duplicate_phone_number(monkeypatch):
    """If another user already registered this phone, creation returns 409 Conflict."""
    mock_db = MockSupabaseClient()
    existing_user_id = uuid4()
    new_user_id = uuid4()
    shared_phone = "+919876543210"

    mock_db.table("patient_profiles").data.append({
        "id": str(uuid4()),
        "patient_id": "MED-2026-EXIST1",
        "user_id": str(existing_user_id),
        "phone_hash": hash_phone(shared_phone),
        "full_name": "Existing Patient",
        "date_of_birth": "1985-05-15",
        "gender": "male",
        "verification_status": "phone_verified",
        "created_at": "2026-10-19T12:00:00Z",
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=new_user_id, phone=shared_phone)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "full_name": "Duplicate Attempt",
            "date_of_birth": "1992-02-02",
            "gender": "male",
        }
        response = client.post("/api/v1/patients/profile", json=payload)
        assert response.status_code == 409
        assert "already associated" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_unauthorized_profile_fields_immutable(monkeypatch):
    """Updating profile only allows blood_group and emergency_contact_phone.

    Immutable identity fields (patient_id, verification_status) are ignored or rejected.
    """
    mock_db = MockSupabaseClient()
    user_id = uuid4()
    original_pid = "MED-2026-IMMUT1"

    mock_db.table("patient_profiles").data.append({
        "id": str(uuid4()),
        "patient_id": original_pid,
        "user_id": str(user_id),
        "full_name": "Original Name",
        "date_of_birth": "1990-01-01",
        "gender": "male",
        "blood_group": "O+",
        "verification_status": "phone_verified",
        "created_at": "2026-10-19T12:00:00Z",
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=user_id, phone="+919876543210")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        # User tries to change blood group and attempts to smuggle patient_id modification
        payload = {
            "blood_group": "AB+",
            "emergency_contact_phone": "+919999900000",
            "patient_id": "MED-2026-HACKED",
            "verification_status": "kyc_verified",
        }
        response = client.patch("/api/v1/patients/me", json=payload)
        assert response.status_code == 200
        data = response.json()
        # Blood group updated
        assert data["blood_group"] == "AB+"
        # Permanent ID remained untouched
        assert data["patient_id"] == original_pid
        assert data["verification_status"] == "phone_verified"
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. Account Recovery Security & Takeover Prevention Tests
# -----------------------------------------------------------------------------
def test_account_recovery_demographic_alone_fails_safely(monkeypatch):
    """Account recovery with demographic knowledge alone must NOT authorize transfer.

    It creates a pending request requiring institutional/hospital desk verification.
    """
    mock_db = MockSupabaseClient()
    owner_user_id = uuid4()
    recovering_user_id = uuid4()
    target_pid = "MED-2026-TARGET1"

    mock_db.table("patient_profiles").data.append({
        "id": str(uuid4()),
        "patient_id": target_pid,
        "user_id": str(owner_user_id),
        "phone_hash": hash_phone("+919999999999"),
        "full_name": "Original Patient",
        "date_of_birth": "1980-08-20",
        "gender": "female",
        "verification_status": "phone_verified",
        "created_at": "2026-10-19T12:00:00Z",
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=recovering_user_id, phone="+917777777777")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "target_patient_id": target_pid,
            "challenge_date_of_birth": "1980-08-20",  # Correct DOB
        }
        response = client.post("/api/v1/patients/recovery/initiate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending_institutional_approval"
        assert "in-person hospital desk verification" in data["message"].lower()

        # Verify profile ownership was NOT changed
        target_in_db = mock_db.table("patient_profiles").data[0]
        assert target_in_db["user_id"] == str(owner_user_id)
    finally:
        app.dependency_overrides.clear()


def test_account_recovery_unapproved_verify_forbidden(monkeypatch):
    """Calling /recovery/verify without staff institutional approval must return 403 Forbidden."""
    mock_db = MockSupabaseClient()
    owner_user_id = uuid4()
    attacker_user_id = uuid4()
    target_profile_id = str(uuid4())
    recovery_req_id = str(uuid4())

    mock_db.table("patient_recovery_requests").data.append({
        "id": recovery_req_id,
        "patient_profile_id": target_profile_id,
        "status": "pending_institutional_approval",  # Not approved by staff!
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=attacker_user_id, phone="+917777777777")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        response = client.post(
            "/api/v1/patients/recovery/verify",
            json={"recovery_request_id": recovery_req_id},
        )
        assert response.status_code == 403
        assert "insufficient" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_recovery_rate_limiting_prevents_brute_force(monkeypatch):
    """Exceeding rate limit on account recovery initiate must return 429 Too Many Requests."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=uuid4(), phone="+917777777777")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "target_patient_id": "MED-2026-FAKE01",
            "challenge_date_of_birth": "1990-01-01",
        }

        # Send 5 attempts (allowed limit)
        for _ in range(5):
            client.post("/api/v1/patients/recovery/initiate", json=payload)

        # 6th attempt must be rejected with 429 Too Many Requests
        response = client.post("/api/v1/patients/recovery/initiate", json=payload)
        assert response.status_code == 429
        assert "rate limit exceeded" in response.json()["detail"].lower()
        assert "Retry-After" in response.headers
    finally:
        app.dependency_overrides.clear()
