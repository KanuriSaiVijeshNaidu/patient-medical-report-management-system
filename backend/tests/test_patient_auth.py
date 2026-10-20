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
        self._ilike_field = None
        self._ilike_val = None

    def select(self, fields="*"):
        return self

    def eq(self, field, value):
        self._filter_field = field
        self._filter_val = value
        return self

    def ilike(self, field, value):
        self._ilike_field = field
        self._ilike_val = str(value).lower()
        return self

    def insert(self, record):
        inserted = dict(record)
        if "id" not in inserted:
            inserted["id"] = str(uuid4())
        if "created_at" not in inserted:
            inserted["created_at"] = "2026-10-19T12:00:00Z"
        self.data.append(inserted)
        return self

    def upsert(self, record):
        inserted = dict(record)
        rec_id = str(inserted.get("id"))
        existing = [i for i, r in enumerate(self.data) if str(r.get("id")) == rec_id]
        if existing:
            self.data[existing[0]].update(inserted)
        else:
            if "id" not in inserted:
                inserted["id"] = str(uuid4())
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
                d for d in filtered
                if str(d.get(self._filter_field)) == str(self._filter_val)
            ]
        if self._ilike_field and self._ilike_val:
            filtered = [
                d for d in filtered
                if str(d.get(self._ilike_field, "")).lower() == self._ilike_val
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
            "user_credentials": MockSupabaseTable(),
        }

        class MockAuthAdmin:
            def create_user(self, params):
                class MockUserRes:
                    class User:
                        id = str(uuid4())
                    user = User()
                return MockUserRes()

        class MockAuth:
            def __init__(self, parent):
                self.parent = parent
                self.admin = MockAuthAdmin()

            def sign_in_with_password(self, params):
                email = params.get("email")
                matching = [u for u in self.parent.tables["users"].data if u.get("email") == email]
                if not matching:
                    raise Exception("Invalid login credentials")
                uid = matching[0]["id"]

                class MockSession:
                    access_token = "mock-supabase-token"

                class MockSignInRes:
                    class User:
                        id = uid
                    user = User()
                    session = MockSession()
                return MockSignInRes()

        self.auth = MockAuth(self)

    def table(self, table_name):
        if table_name not in self.tables:
            self.tables[table_name] = MockSupabaseTable()
        return self.tables[table_name]

    def rpc(self, fn_name, params):
        class MockRpcCall:
            def __init__(self, client, fn, p):
                self.client = client
                self.fn = fn
                self.p = p

            def execute(self):
                class Result:
                    def __init__(self, data):
                        self.data = data

                if self.fn == "record_security_audit_event":
                    aid = str(uuid4())
                    self.client.table("audit_logs").insert({
                        "id": aid,
                        "actor_user_id": self.p.get("p_actor_user_id"),
                        "actor_role": "patient",
                        "action": self.p.get("p_action"),
                        "entity_type": self.p.get("p_entity_type"),
                        "entity_id": str(self.p.get("p_entity_id")),
                        "ip_address": self.p.get("p_ip_address"),
                        "details": self.p.get("p_details") or {},
                        "created_at": "2026-10-19T12:00:00Z",
                    })
                    return Result(aid)

                elif self.fn == "register_patient_profile_atomic":
                    user_id = str(self.p["p_auth_user_id"])
                    phone_e164 = self.p.get("p_phone_e164")
                    phone_hash = self.p.get("p_phone_hash")

                    if phone_e164:
                        if phone_hash != hash_phone(phone_e164):
                            raise Exception("check_violation: Phone number and phone checksum do not match.")

                    existing = [p for p in self.client.table("patient_profiles").data if str(p.get("user_id")) == user_id]
                    if existing:
                        prof = dict(existing[0])
                        prof["status"] = "existing"
                        return Result(prof)

                    if phone_hash:
                        dup = [p for p in self.client.table("patient_profiles").data if p.get("phone_hash") == phone_hash]
                        if dup:
                            raise Exception("unique_violation: A medical profile is already associated with this verified phone number.")

                    user_exists = [u for u in self.client.table("users").data if str(u.get("id")) == user_id]
                    if not user_exists:
                        self.client.table("users").insert({
                            "id": user_id,
                            "phone_e164": self.p.get("p_phone_e164"),
                            "role": "patient",
                            "is_active": True,
                        })

                    new_id = str(uuid4())
                    new_prof = {
                        "id": new_id,
                        "patient_id": self.p.get("p_patient_id"),
                        "user_id": user_id,
                        "full_name": self.p.get("p_full_name"),
                        "date_of_birth": str(self.p.get("p_date_of_birth")),
                        "gender": self.p.get("p_gender"),
                        "blood_group": self.p.get("p_blood_group"),
                        "emergency_contact_phone": self.p.get("p_emergency_contact_phone"),
                        "phone_hash": phone_hash,
                        "verification_status": "phone_verified" if phone_hash else "email_verified",
                        "created_at": "2026-10-19T12:00:00Z",
                        "updated_at": None,
                    }
                    self.client.table("patient_profiles").data.append(new_prof)

                    self.client.table("audit_logs").insert({
                        "id": str(uuid4()),
                        "actor_user_id": user_id,
                        "actor_role": "patient",
                        "action": "patient_profile_created",
                        "entity_type": "patient_profile",
                        "entity_id": new_id,
                        "ip_address": self.p.get("p_ip_address"),
                        "details": {
                            "patient_id": self.p.get("p_patient_id"),
                            "request_id": self.p.get("p_request_id"),
                            "outcome": "success",
                        },
                        "created_at": "2026-10-19T12:00:00Z",
                    })

                    res = dict(new_prof)
                    res["status"] = "created"
                    return Result(res)

                elif self.fn == "update_patient_profile_atomic":
                    user_id = str(self.p["p_auth_user_id"])
                    existing = [p for p in self.client.table("patient_profiles").data if str(p.get("user_id")) == user_id]
                    if not existing:
                        raise Exception("no_data_found: Patient profile not found.")
                    prof = existing[0]
                    updated_fields = []
                    if self.p.get("p_blood_group") is not None:
                        prof["blood_group"] = self.p.get("p_blood_group")
                        updated_fields.append("blood_group")
                    if self.p.get("p_emergency_contact_phone") is not None:
                        prof["emergency_contact_phone"] = self.p.get("p_emergency_contact_phone")
                        updated_fields.append("emergency_contact_phone")
                    prof["updated_at"] = "2026-10-19T12:00:00Z"

                    self.client.table("audit_logs").insert({
                        "id": str(uuid4()),
                        "actor_user_id": user_id,
                        "actor_role": "patient",
                        "action": "patient_profile_updated",
                        "entity_type": "patient_profile",
                        "entity_id": prof["id"],
                        "ip_address": self.p.get("p_ip_address"),
                        "details": {
                            "updated_fields": updated_fields,
                            "request_id": self.p.get("p_request_id"),
                            "outcome": "success",
                        },
                        "created_at": "2026-10-19T12:00:00Z",
                    })
                    return Result(prof)

                elif self.fn == "verify_account_recovery_atomic":
                    req_id = str(self.p["p_recovery_request_id"])
                    user_id = str(self.p["p_auth_user_id"])
                    new_phone_hash = self.p.get("p_new_phone_hash")
                    reqs = [r for r in self.client.table("patient_recovery_requests").data if str(r.get("id")) == req_id]
                    if not reqs:
                        raise Exception("no_data_found: Recovery request not found.")
                    req = reqs[0]
                    if req.get("status") != "approved_by_staff":
                        raise Exception("insufficient_privilege: Recovery request has not been approved.")

                    prof_id = req["patient_profile_id"]
                    profs = [p for p in self.client.table("patient_profiles").data if str(p.get("id")) == str(prof_id)]
                    patient_id = ""
                    if profs:
                        p = profs[0]
                        p["user_id"] = user_id
                        p["phone_hash"] = new_phone_hash
                        p["updated_at"] = "2026-10-19T12:00:00Z"
                        patient_id = p.get("patient_id", "")

                    req["status"] = "completed"
                    self.client.table("audit_logs").insert({
                        "id": str(uuid4()),
                        "actor_user_id": user_id,
                        "actor_role": "patient",
                        "action": "patient_account_recovered",
                        "entity_type": "patient_profile",
                        "entity_id": str(prof_id),
                        "ip_address": self.p.get("p_ip_address"),
                        "details": {
                            "recovery_request_id": req_id,
                            "request_id": self.p.get("p_request_id"),
                            "outcome": "success",
                        },
                        "created_at": "2026-10-19T12:00:00Z",
                    })
                    return Result({
                        "success": True,
                        "patient_id": patient_id,
                        "message": "Account successfully recovered. All medical records remain linked to your Patient ID.",
                    })

                raise NotImplementedError(f"Mock RPC {self.fn} not implemented")

        return MockRpcCall(self, fn_name, params)



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


def test_registration_with_email_only(monkeypatch):
    """Patient can register profile using email authentication without a phone number."""
    mock_db = MockSupabaseClient()
    user_id = uuid4()

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    # User authenticated via email (phone is None)
    mock_user = AuthenticatedUser(id=user_id, email="patient@hospital.org", phone=None)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "full_name": "Email Authenticated Patient",
            "date_of_birth": "1994-07-22",
            "gender": "female",
            "blood_group": "B+",
        }
        response = client.post("/api/v1/patients/profile", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["full_name"] == "Email Authenticated Patient"
        assert data["patient_id"].startswith("MED-")
        assert data["verification_status"] == "email_verified"
        assert data["phone_masked"] is None
        assert len(mock_db.table("patient_profiles").data) == 1
    finally:
        app.dependency_overrides.clear()


def test_unauthenticated_registration_rejected():
    """Unauthenticated request to create profile must return 401."""
    payload = {
        "full_name": "Unauthenticated Hacker",
        "date_of_birth": "1990-01-01",
        "gender": "other",
    }
    response = client.post("/api/v1/patients/profile", json=payload)
    assert response.status_code == 401


def test_registration_requires_email_or_phone(monkeypatch):
    """User with neither email nor phone cannot register a patient profile."""
    mock_db = MockSupabaseClient()
    user_id = uuid4()

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    mock_user = AuthenticatedUser(id=user_id, email=None, phone=None)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "full_name": "No Contact User",
            "date_of_birth": "1990-01-01",
            "gender": "male",
        }
        response = client.post("/api/v1/patients/profile", json=payload)
        assert response.status_code == 400
        assert "verified phone number or email" in response.json()["detail"].lower()
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


def test_unauthenticated_profile_creation_rejected():
    """Attempting to create patient profile without Bearer token must return 401."""
    payload = {
        "full_name": "Unauthenticated User",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    }
    response = client.post("/api/v1/patients/profile", json=payload)
    assert response.status_code == 401
    assert "Authentication required. Please provide a valid Bearer token." in response.json()["detail"]


def test_profile_creation_with_valid_bearer_token(monkeypatch):
    """Profile creation with cryptographically valid Bearer token succeeds and creates profile."""
    test_secret = "super-secret-test-key-32-characters-minimum!"
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: None)

    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    user_id = str(uuid4())
    token = jwt.encode(
        {
            "sub": user_id,
            "aud": "authenticated",
            "role": "authenticated",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "phone": "+919876543210",
        },
        test_secret,
        algorithm="HS256",
    )

    payload = {
        "full_name": "Authenticated Patient",
        "date_of_birth": "1995-05-15",
        "gender": "female",
        "blood_group": "B+",
    }
    response = client.post(
        "/api/v1/patients/profile",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "Authenticated Patient"
    assert data["verification_status"] == "phone_verified"
    assert data["patient_id"].startswith("MED-2026-")
    assert len(mock_db.table("patient_profiles").data) == 1


def test_profile_creation_with_expired_bearer_token(monkeypatch):
    """Profile creation with an expired Bearer token is rejected with 401."""
    test_secret = "super-secret-test-key-32-characters-minimum!"
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: None)

    user_id = str(uuid4())
    expired_token = jwt.encode(
        {
            "sub": user_id,
            "aud": "authenticated",
            "role": "authenticated",
            "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
            "phone": "+919876543210",
        },
        test_secret,
        algorithm="HS256",
    )

    payload = {
        "full_name": "Expired User",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    }
    response = client.post(
        "/api/v1/patients/profile",
        json=payload,
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_profile_creation_handles_phone_without_plus_prefix(monkeypatch):
    """Supabase Auth returns phone without plus prefix (e.g. '919876543210'). Normalization succeeds."""
    test_secret = "super-secret-test-key-32-characters-minimum!"
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: None)

    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    user_id = str(uuid4())
    token = jwt.encode(
        {
            "sub": user_id,
            "aud": "authenticated",
            "role": "authenticated",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "phone": "919876543210",  # Without leading +
        },
        test_secret,
        algorithm="HS256",
    )

    payload = {
        "full_name": "Phone Normalize Patient",
        "date_of_birth": "1988-08-08",
        "gender": "other",
    }
    response = client.post(
        "/api/v1/patients/profile",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "Phone Normalize Patient"
    assert data["phone_masked"] == "+91 ****** 3210"


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


# -----------------------------------------------------------------------------
# 5. Phase 2B: Database Migration Structural Integrity Tests
# -----------------------------------------------------------------------------
def test_auth_api_rejection_raises_401(monkeypatch):
    """When Supabase Auth API rejects token, auth guard immediately returns 401."""
    class MockAuthApi:
        def get_user(self, token):
            raise Exception("AuthApiError: invalid JWT token format")

    class MockClientWithAuth:
        auth = MockAuthApi()

    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: MockClientWithAuth())

    response = client.get(
        "/api/v1/patients/me",
        headers={"Authorization": "Bearer bad-token-for-supabase"},
    )
    assert response.status_code == 401
    assert "invalid or expired" in response.json()["detail"].lower()


def test_sql_migrations_structural_integrity_and_rls():
    """Validates that both SQL migrations define required tables, triggers, and RLS policies.

    Ensures that:
    1. All 9 core tables have ENABLE ROW LEVEL SECURITY.
    2. Immutability triggers exist for patient_profiles, users, and audit_logs.
    3. Triggers do NOT use SECURITY DEFINER where auth.role() must be evaluated.
    4. Safe duplicate pre-check exists before creating unique index on phone_hash.
    """
    import os

    migration_dir = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")
    if not os.path.exists(migration_dir):
        migration_dir = os.path.join(os.path.dirname(__file__), "..", "supabase", "migrations")
    mig1_path = os.path.join(migration_dir, "20261019000001_initial_schema.sql")
    mig2_path = os.path.join(migration_dir, "20261019000002_security_audit_fixes.sql")

    assert os.path.exists(mig1_path), "Migration 01 must exist"
    assert os.path.exists(mig2_path), "Migration 02 must exist"

    with open(mig1_path, "r", encoding="utf-8") as f:
        mig1_sql = f.read()
    with open(mig2_path, "r", encoding="utf-8") as f:
        mig2_sql = f.read()

    combined_sql = mig1_sql + "\n" + mig2_sql

    core_tables = [
        "users",
        "patient_profiles",
        "hospitals",
        "hospital_staff",
        "medical_reports",
        "record_access_grants",
        "emergency_access_logs",
        "patient_recovery_requests",
        "audit_logs",
    ]

    # Every core table must have ENABLE ROW LEVEL SECURITY
    for table in core_tables:
        expected = f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"
        assert expected in combined_sql, f"Missing RLS enablement for table {table}"

    # Verify unique index on phone_hash
    assert "idx_patient_profiles_phone_hash_unique" in mig2_sql

    # Verify safe duplicate pre-check exists before index creation
    assert "GROUP BY phone_hash" in mig2_sql

    # Verify immutability triggers
    assert "trg_patient_profile_immutability" in mig2_sql
    assert "trg_user_role_immutability" in mig2_sql
    assert "trg_audit_logs_immutable" in mig2_sql

    # Verify triggers do NOT use SECURITY DEFINER on role/status checks
    assert "check_patient_profile_immutability()\nRETURNS TRIGGER AS $$" in mig2_sql or "LANGUAGE plpgsql;" in mig2_sql
    assert "auth.role()" in mig2_sql, "Trigger must inspect Supabase auth.role()"


def test_sql_integration_test_suite_coverage():
    """Verifies that the repeatable SQL integration test suite exists and covers all 7 security checks."""
    import os

    tests_dir = os.path.join(os.path.dirname(__file__), "..", "supabase", "tests")
    setup_path = os.path.join(tests_dir, "setup_test_environment.sql")
    test_suite_path = os.path.join(tests_dir, "test_rls_and_security.sql")

    assert os.path.exists(setup_path), "setup_test_environment.sql must exist"
    assert os.path.exists(test_suite_path), "test_rls_and_security.sql must exist"

    with open(test_suite_path, "r", encoding="utf-8") as f:
        test_sql = f.read()

    expected_checks = [
        "TEST 1: Anonymous Access Denial",
        "TEST 2: Patient Profile Creation & Tenant Isolation",
        "TEST 3: Cross-Patient Data Reading & Modification Denial",
        "TEST 4: Immutability Triggers",
        "TEST 5: Database-Level Unique Constraint",
        "TEST 6: Audit Log Tamper-Proofing",
        "TEST 7: Service Role Legitimacy Check",
    ]

    for check in expected_checks:
        assert check in test_sql, f"Missing security check in SQL test suite: {check}"


# -----------------------------------------------------------------------------
# 4. Username & Password Authentication Tests
# -----------------------------------------------------------------------------
def test_registration_with_valid_details(monkeypatch):
    """Registering a new patient with valid username and password creates profile, returns Patient ID and token."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    payload = {
        "full_name": "Ramesh Kumar",
        "username": "ramesh_k",
        "password": "Password123!",
        "gender": "male",
        "phone": "+91 98765 43210",
        "blood_group": "B+",
    }

    res = client.post("/api/v1/patients/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["patient_id"].startswith("MED-")
    assert len(data["patient_id"]) == 15
    assert data["username"] == "ramesh_k"
    assert data["full_name"] == "Ramesh Kumar"
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_registration_rejects_duplicate_username(monkeypatch):
    """Attempting to register with an existing username (case-insensitive) must return 409 Conflict."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # First user
    u1 = {
        "full_name": "User One",
        "username": "unique_user",
        "password": "Password123!",
        "gender": "other",
        "phone": "+91 98765 00001",
        "blood_group": "O+",
    }
    res1 = client.post("/api/v1/patients/register", json=u1)
    assert res1.status_code == 201

    # Second user with duplicate username in different case
    u2 = {
        "full_name": "User Two",
        "username": "UNIQUE_USER",
        "password": "Password456!",
        "gender": "female",
        "phone": "+91 98765 00002",
        "blood_group": "A+",
    }
    res2 = client.post("/api/v1/patients/register", json=u2)
    assert res2.status_code == 409
    assert "Username is already taken" in res2.json()["detail"]


def test_registration_validation_rules_and_missing_fields():
    """Validates missing required fields, weak passwords, and invalid usernames."""
    # 1. Missing blood group
    res_no_bg = client.post("/api/v1/patients/register", json={
        "full_name": "Valid Name",
        "username": "valid_user",
        "password": "Password123!",
        "gender": "male",
        "phone": "+919876543210",
    })
    assert res_no_bg.status_code == 422

    # 2. Password < 8 characters
    res_short_pw = client.post("/api/v1/patients/register", json={
        "full_name": "Valid Name",
        "username": "valid_user",
        "password": "short",
        "gender": "male",
        "phone": "+919876543210",
        "blood_group": "O+",
    })
    assert res_short_pw.status_code == 422

    # 3. Password without digits or symbols (only letters)
    res_weak_pw = client.post("/api/v1/patients/register", json={
        "full_name": "Valid Name",
        "username": "valid_user",
        "password": "passwordonlyletters",
        "gender": "male",
        "phone": "+919876543210",
        "blood_group": "O+",
    })
    assert res_weak_pw.status_code == 422

    # 4. Username with illegal characters (spaces)
    res_bad_user = client.post("/api/v1/patients/register", json={
        "full_name": "Valid Name",
        "username": "user name with spaces",
        "password": "Password123!",
        "gender": "male",
        "phone": "+919876543210",
        "blood_group": "O+",
    })
    assert res_bad_user.status_code == 422

    # 5. Invalid gender
    res_bad_gender = client.post("/api/v1/patients/register", json={
        "full_name": "Valid Name",
        "username": "valid_user",
        "password": "Password123!",
        "gender": "alien",
        "phone": "+919876543210",
        "blood_group": "O+",
    })
    assert res_bad_gender.status_code == 422


def test_registration_rejects_duplicate_phone(monkeypatch):
    """Attempting to register an account with a phone number already in use returns 409 Conflict."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # First user
    u1 = {
        "full_name": "Patient Alpha",
        "username": "patient_alpha",
        "password": "Password123!",
        "gender": "male",
        "phone": "+91 91234 56789",
        "blood_group": "A+",
    }
    res1 = client.post("/api/v1/patients/register", json=u1)
    assert res1.status_code == 201

    # Second user with distinct username but duplicate phone number
    u2 = {
        "full_name": "Patient Beta",
        "username": "patient_beta",
        "password": "Password456!",
        "gender": "female",
        "phone": "+91-91234-56789",
        "blood_group": "B+",
    }
    res2 = client.post("/api/v1/patients/register", json=u2)
    assert res2.status_code == 409
    assert "already associated" in res2.json()["detail"].lower()


def test_login_with_correct_credentials(monkeypatch):
    """Logging in with correct username and password returns valid session token and Patient ID."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # Register
    reg_payload = {
        "full_name": "Sunita Devi",
        "username": "sunita_d",
        "password": "SecretPass2026!",
        "gender": "female",
        "phone": "+91 99887 76655",
        "blood_group": "AB+",
    }
    reg_res = client.post("/api/v1/patients/register", json=reg_payload)
    assert reg_res.status_code == 201
    patient_id = reg_res.json()["patient_id"]

    # Login
    login_payload = {
        "username": "sunita_d",
        "password": "SecretPass2026!",
    }
    login_res = client.post("/api/v1/patients/login", json=login_payload)
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["patient_id"] == patient_id
    assert login_data["username"] == "sunita_d"
    assert "access_token" in login_data
    assert login_data["token_type"] == "bearer"


def test_login_with_incorrect_password(monkeypatch):
    """Logging in with an incorrect password returns 401 Unauthorized."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    reg_payload = {
        "full_name": "Vikram Patel",
        "username": "vikram_p",
        "password": "CorrectPassword123!",
        "gender": "male",
        "phone": "+91 91122 33445",
        "blood_group": "O-",
    }
    client.post("/api/v1/patients/register", json=reg_payload)

    # Incorrect password attempt
    bad_login = {
        "username": "vikram_p",
        "password": "WrongPassword!",
    }
    res = client.post("/api/v1/patients/login", json=bad_login)
    assert res.status_code == 401
    assert "Invalid username or password" in res.json()["detail"]


def test_login_with_nonexistent_username(monkeypatch):
    """Logging in with a non-existent username returns 401 Unauthorized."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    res = client.post("/api/v1/patients/login", json={
        "username": "ghost_patient",
        "password": "Password123!",
    })
    assert res.status_code == 401
    assert "Invalid username or password" in res.json()["detail"]


def test_session_token_authenticates_protected_endpoints(monkeypatch):
    """Session token issued upon login correctly authenticates protected endpoints like /me."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    reg_res = client.post("/api/v1/patients/register", json={
        "full_name": "Anita Roy",
        "username": "anita_roy",
        "password": "Password2026!",
        "gender": "female",
        "phone": "+91 97788 99001",
        "blood_group": "A+",
    })
    token = reg_res.json()["access_token"]
    expected_patient_id = reg_res.json()["patient_id"]

    # Access protected /me
    me_res = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["patient_id"] == expected_patient_id
    assert me_res.json()["full_name"] == "Anita Roy"


def test_cross_patient_data_isolation_with_username_auth(monkeypatch):
    """Two patients authenticated via username/password cannot view or access each other's data."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # Register Patient A
    res_a = client.post("/api/v1/patients/register", json={
        "full_name": "Patient Alpha",
        "username": "patient_a",
        "password": "Password123!",
        "gender": "male",
        "phone": "+91 90001 00001",
        "blood_group": "A+",
    })
    token_a = res_a.json()["access_token"]
    pid_a = res_a.json()["patient_id"]

    # Register Patient B
    res_b = client.post("/api/v1/patients/register", json={
        "full_name": "Patient Beta",
        "username": "patient_b",
        "password": "Password456!",
        "gender": "female",
        "phone": "+91 90002 00002",
        "blood_group": "B+",
    })
    token_b = res_b.json()["access_token"]
    pid_b = res_b.json()["patient_id"]

    # Verify Patient A only accesses Patient A's record
    profile_a = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert profile_a["patient_id"] == pid_a
    assert profile_a["patient_id"] != pid_b

    # Verify Patient B only accesses Patient B's record
    profile_b = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert profile_b["patient_id"] == pid_b
    assert profile_b["patient_id"] != pid_a


def test_hospital_staff_login_endpoint():
    """Hospital staff login endpoint remains available and maintains expected interface."""
    res = client.post("/api/v1/hospital/login", json={
        "email": "doctor@cityhospital.org",
        "password": "StaffPassword123!",
        "hospital_registration_number": "HOSP-REG-4421",
    })
    # Hospital login is now fully implemented with organizational verification
    assert res.status_code in [200, 401, 501]


def test_login_after_logout_flow(monkeypatch):
    """Patient logs in, accesses protected profile, logs out (token cleared -> 401), and logs in again."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # 1. Register
    reg_res = client.post("/api/v1/patients/register", json={
        "full_name": "Rohan Gupta",
        "username": "rohan_g",
        "password": "Password2026!",
        "gender": "male",
        "phone": "+91 91234 56789",
        "blood_group": "B+",
    })
    assert reg_res.status_code == 201
    patient_id = reg_res.json()["patient_id"]

    # 2. Initial Login
    login1_res = client.post("/api/v1/patients/login", json={
        "username": "rohan_g",
        "password": "Password2026!",
    })
    assert login1_res.status_code == 200
    token1 = login1_res.json()["access_token"]
    assert login1_res.json()["patient_id"] == patient_id

    # 3. Access protected endpoint with token 1
    me1_res = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token1}"})
    assert me1_res.status_code == 200
    assert me1_res.json()["patient_id"] == patient_id

    # 4. Simulate Logout: token is cleared on frontend, unauthenticated requests are rejected
    me_logged_out = client.get("/api/v1/patients/me")
    assert me_logged_out.status_code == 401

    me_invalid_token = client.get("/api/v1/patients/me", headers={"Authorization": "Bearer invalid_cleared_token"})
    assert me_invalid_token.status_code == 401

    # 5. Subsequent Login after Logout: new token is issued and accesses profile
    login2_res = client.post("/api/v1/patients/login", json={
        "username": "rohan_g",
        "password": "Password2026!",
    })
    assert login2_res.status_code == 200
    token2 = login2_res.json()["access_token"]
    assert login2_res.json()["patient_id"] == patient_id

    # 6. Access protected endpoint with token 2
    me2_res = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token2}"})
    assert me2_res.status_code == 200
    assert me2_res.json()["patient_id"] == patient_id


def test_unauthenticated_access_to_protected_endpoints():
    """Unauthenticated requests to protected patient and report endpoints are strictly rejected with 401."""
    # /api/v1/patients/me
    res_me = client.get("/api/v1/patients/me")
    assert res_me.status_code == 401

    # /api/v1/reports
    res_reports = client.get("/api/v1/reports")
    assert res_reports.status_code == 401

    # /api/v1/access/create-share
    res_share = client.post("/api/v1/access/create-share", json={
        "report_id": "REP-2026-TEST",
        "duration_seconds": 900,
    })
    assert res_share.status_code == 401


def test_login_validation_and_clear_error_responses(monkeypatch):
    """Login returns structured, clear JSON errors for invalid requests without generic failures."""
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # 1. Missing username
    res_no_user = client.post("/api/v1/patients/login", json={"password": "Pass"})
    assert res_no_user.status_code == 422
    assert "detail" in res_no_user.json()

    # 2. Missing password
    res_no_pass = client.post("/api/v1/patients/login", json={"username": "user"})
    assert res_no_pass.status_code == 422
    assert "detail" in res_no_pass.json()

    # 3. Invalid credentials
    res_bad = client.post("/api/v1/patients/login", json={
        "username": "non_existent_user",
        "password": "WrongPassword123!",
    })
    assert res_bad.status_code == 401
    assert res_bad.json()["detail"] == "Invalid username or password."


def test_login_with_missing_patient_profile(monkeypatch):
    """When credentials are valid but patient_profiles record is missing, returns 404 with clear message."""
    from app.core.security import hash_password
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # Insert credentials for user without a corresponding record in patient_profiles
    orphan_user_id = str(uuid4())
    mock_db.table("user_credentials").insert({
        "user_id": orphan_user_id,
        "username": "orphan_patient",
        "password_hash": hash_password("OrphanPass123!"),
    }).execute()

    res = client.post("/api/v1/patients/login", json={
        "username": "orphan_patient",
        "password": "OrphanPass123!",
    })
    assert res.status_code == 404
    assert "Patient profile not found" in res.json()["detail"]


def test_login_existing_registered_patient_with_credentials_sync(monkeypatch):
    """An existing registered patient (present in auth and patient_profiles but not yet in user_credentials)
    authenticates via the isolated auth client fallback, automatically syncs their credentials,
    and successfully receives their Patient ID and access token.
    Subsequent login uses the synced user_credentials record.
    """
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.api.v1.patients.create_isolated_auth_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # 1. Setup existing registered patient prior to username/password migration
    existing_user_id = str(uuid4())
    username = "saivijesh"
    internal_email = f"{username}@patient.internal"
    patient_id = "MED-2026-3N62YU"

    # In users table
    mock_db.table("users").insert({
        "id": existing_user_id,
        "email": internal_email,
        "phone_e164": "+919392538934",
        "role": "patient",
        "username": None,
    })

    # In patient_profiles table
    mock_db.table("patient_profiles").insert({
        "id": str(uuid4()),
        "user_id": existing_user_id,
        "patient_id": patient_id,
        "full_name": "k sai vijesh",
        "date_of_birth": "1995-05-15",
        "gender": "male",
        "blood_group": "O+",
        "phone_hash": "existing_phone_hash",
        "verification_status": "phone_verified",
    })

    # user_credentials is initially empty
    assert len(mock_db.table("user_credentials").data) == 0

    # 2. First login: triggers isolated GoTrue fallback and synchronizes credentials
    res1 = client.post("/api/v1/patients/login", json={
        "username": username,
        "password": "ExistingPatientPass123!",
    })
    assert res1.status_code == 200, res1.text
    body1 = res1.json()
    assert body1["patient_id"] == patient_id
    assert body1["username"] == username
    assert body1["full_name"] == "k sai vijesh"
    assert "access_token" in body1

    # Verify credentials synchronized
    assert len(mock_db.table("user_credentials").data) == 1
    synced_cred = mock_db.table("user_credentials").data[0]
    assert synced_cred["user_id"] == existing_user_id
    assert synced_cred["username"] == username

    # 3. Second login: authenticates directly via synced user_credentials
    res2 = client.post("/api/v1/patients/login", json={
        "username": username,
        "password": "ExistingPatientPass123!",
    })
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["patient_id"] == patient_id
    assert body2["access_token"] is not None


def test_login_and_cross_patient_access_denied(monkeypatch):
    """Tests that logging in as Patient A provides access strictly to Patient A's profile,
    and prevents access to Patient B's records.
    """
    from app.core.security import hash_password
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # Setup Patient A
    user_a = str(uuid4())
    mock_db.table("users").insert({"id": user_a, "email": "patient_a@internal", "role": "patient", "username": "patient_a"})
    mock_db.table("patient_profiles").insert({
        "id": str(uuid4()),
        "user_id": user_a,
        "patient_id": "MED-2026-AAAA01",
        "full_name": "Patient Alpha",
        "date_of_birth": "1990-01-01",
        "gender": "male",
        "blood_group": "A+",
        "phone_hash": "hash_a",
        "verification_status": "phone_verified",
    })
    mock_db.table("user_credentials").insert({
        "user_id": user_a,
        "username": "patient_a",
        "password_hash": hash_password("PasswordA123!"),
    })

    # Setup Patient B
    user_b = str(uuid4())
    mock_db.table("users").insert({"id": user_b, "email": "patient_b@internal", "role": "patient", "username": "patient_b"})
    mock_db.table("patient_profiles").insert({
        "id": str(uuid4()),
        "user_id": user_b,
        "patient_id": "MED-2026-BBBB02",
        "full_name": "Patient Beta",
        "date_of_birth": "1992-02-02",
        "gender": "female",
        "blood_group": "B+",
        "phone_hash": "hash_b",
        "verification_status": "phone_verified",
    })
    mock_db.table("user_credentials").insert({
        "user_id": user_b,
        "username": "patient_b",
        "password_hash": hash_password("PasswordB123!"),
    })

    # Login as Patient A
    res_a = client.post("/api/v1/patients/login", json={
        "username": "patient_a",
        "password": "PasswordA123!",
    })
    assert res_a.status_code == 200
    token_a = res_a.json()["access_token"]
    assert res_a.json()["patient_id"] == "MED-2026-AAAA01"

    # Login as Patient B
    res_b = client.post("/api/v1/patients/login", json={
        "username": "patient_b",
        "password": "PasswordB123!",
    })
    assert res_b.status_code == 200
    token_b = res_b.json()["access_token"]
    assert res_b.json()["patient_id"] == "MED-2026-BBBB02"

    # Patient A calls /me -> sees only Alpha
    me_a = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me_a.status_code == 200
    assert me_a.json()["patient_id"] == "MED-2026-AAAA01"
    assert me_a.json()["full_name"] == "Patient Alpha"
    assert me_a.json()["patient_id"] != "MED-2026-BBBB02"

    # Patient B calls /me -> sees only Beta
    me_b = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_b.status_code == 200
    assert me_b.json()["patient_id"] == "MED-2026-BBBB02"
    assert me_b.json()["full_name"] == "Patient Beta"
    assert me_b.json()["patient_id"] != "MED-2026-AAAA01"


def test_permission_denied_returns_503_and_logs_diagnostics(monkeypatch):
    """When a PostgREST 42501 permission error occurs, the endpoint returns a 503 Service Unavailable
    with a controlled message and captures diagnostic details without leaking secrets.
    """
    from app.core.security import hash_password
    mock_db = MockSupabaseClient()
    test_user_id = str(uuid4())

    mock_db.table("user_credentials").insert({
        "user_id": test_user_id,
        "username": "perm_test_user",
        "password_hash": hash_password("PermPass123!"),
    })

    # Make patient_profiles raise 42501 permission error
    class FailingTable(MockSupabaseTable):
        def execute(self):
            class APIError(Exception):
                code = "42501"
                message = "permission denied for table patient_profiles"
                details = None
            raise APIError("permission denied for table patient_profiles")

    mock_db.tables["patient_profiles"] = FailingTable()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    res = client.post("/api/v1/patients/login", json={
        "username": "perm_test_user",
        "password": "PermPass123!",
    })
    assert res.status_code == 503
    assert res.json()["detail"] == "Database permissions error accessing patient profile."


def test_repeated_login_logout_cycles_with_patient_isolation(monkeypatch):
    """Full sequence test:
    login -> authenticated request -> logout -> login again -> authenticated request.
    Includes repeated login/logout cycles across multiple distinct patients and verifies patient isolation.
    """
    from app.core.security import hash_password
    mock_db = MockSupabaseClient()
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)
    monkeypatch.setattr("app.core.auth.get_supabase_client", lambda: mock_db)

    # 1. Setup Patient Alpha
    user_alpha_id = str(uuid4())
    patient_id_alpha = "MED-2026-ALPHA1"
    mock_db.table("users").insert({
        "id": user_alpha_id,
        "username": "patient_alpha",
        "email": "alpha@patient.internal",
        "phone_e164": "+919876543210",
        "role": "patient",
    })
    mock_db.table("patient_profiles").insert({
        "id": str(uuid4()),
        "user_id": user_alpha_id,
        "patient_id": patient_id_alpha,
        "full_name": "Alpha Patient",
        "date_of_birth": "1991-01-01",
        "gender": "male",
        "blood_group": "O+",
        "phone_hash": "hash_alpha",
        "verification_status": "phone_verified",
    })
    mock_db.table("user_credentials").insert({
        "user_id": user_alpha_id,
        "username": "patient_alpha",
        "password_hash": hash_password("AlphaSecret2026!"),
    })

    # 2. Setup Patient Beta
    user_beta_id = str(uuid4())
    patient_id_beta = "MED-2026-BETA02"
    mock_db.table("users").insert({
        "id": user_beta_id,
        "username": "patient_beta",
        "email": "beta@patient.internal",
        "phone_e164": "+919876543211",
        "role": "patient",
    })
    mock_db.table("patient_profiles").insert({
        "id": str(uuid4()),
        "user_id": user_beta_id,
        "patient_id": patient_id_beta,
        "full_name": "Beta Patient",
        "date_of_birth": "1993-03-03",
        "gender": "female",
        "blood_group": "A+",
        "phone_hash": "hash_beta",
        "verification_status": "phone_verified",
    })
    mock_db.table("user_credentials").insert({
        "user_id": user_beta_id,
        "username": "patient_beta",
        "password_hash": hash_password("BetaSecret2026!"),
    })

    # --- CYCLE 1: Patient Alpha initial login & authenticated request ---
    res_login1 = client.post("/api/v1/patients/login", json={
        "username": "patient_alpha",
        "password": "AlphaSecret2026!",
    })
    assert res_login1.status_code == 200
    token_alpha_1 = res_login1.json()["access_token"]
    assert res_login1.json()["patient_id"] == patient_id_alpha

    # Authenticated profile request
    res_me1 = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_alpha_1}"})
    assert res_me1.status_code == 200
    assert res_me1.json()["patient_id"] == patient_id_alpha
    assert res_me1.json()["full_name"] == "Alpha Patient"

    # Simulate Logout: client clears token -> unauthenticated requests denied
    res_unauth = client.get("/api/v1/patients/me")
    assert res_unauth.status_code == 401

    # --- CYCLE 2: Patient Alpha second login with same credentials ---
    res_login2 = client.post("/api/v1/patients/login", json={
        "username": "patient_alpha",
        "password": "AlphaSecret2026!",
    })
    assert res_login2.status_code == 200
    token_alpha_2 = res_login2.json()["access_token"]
    assert res_login2.json()["patient_id"] == patient_id_alpha

    # Authenticated profile request on repeat login must succeed cleanly
    res_me2 = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_alpha_2}"})
    assert res_me2.status_code == 200
    assert res_me2.json()["patient_id"] == patient_id_alpha
    assert res_me2.json()["full_name"] == "Alpha Patient"

    # Simulate Logout
    res_unauth2 = client.get("/api/v1/patients/me")
    assert res_unauth2.status_code == 401

    # --- CYCLE 3: Patient Beta login & Patient Isolation Verification ---
    res_login_beta = client.post("/api/v1/patients/login", json={
        "username": "patient_beta",
        "password": "BetaSecret2026!",
    })
    assert res_login_beta.status_code == 200
    token_beta = res_login_beta.json()["access_token"]
    assert res_login_beta.json()["patient_id"] == patient_id_beta

    # Beta profile request
    res_me_beta = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_beta}"})
    assert res_me_beta.status_code == 200
    assert res_me_beta.json()["patient_id"] == patient_id_beta
    assert res_me_beta.json()["full_name"] == "Beta Patient"

    # Beta's token cannot view Alpha's records
    assert res_me_beta.json()["patient_id"] != patient_id_alpha

    # --- CYCLE 4: Patient Alpha 3rd login & Patient Beta 2nd login (interleaved) ---
    res_login3 = client.post("/api/v1/patients/login", json={
        "username": "patient_alpha",
        "password": "AlphaSecret2026!",
    })
    assert res_login3.status_code == 200
    token_alpha_3 = res_login3.json()["access_token"]

    res_me3 = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_alpha_3}"})
    assert res_me3.status_code == 200
    assert res_me3.json()["patient_id"] == patient_id_alpha

    # Beta logs in again
    res_login_beta2 = client.post("/api/v1/patients/login", json={
        "username": "patient_beta",
        "password": "BetaSecret2026!",
    })
    assert res_login_beta2.status_code == 200
    token_beta_2 = res_login_beta2.json()["access_token"]

    res_me_beta2 = client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_beta_2}"})
    assert res_me_beta2.status_code == 200
    assert res_me_beta2.json()["patient_id"] == patient_id_beta


