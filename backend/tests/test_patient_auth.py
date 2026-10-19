from datetime import date
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import generate_patient_id, normalize_phone, hash_phone, mask_phone
from app.core.auth import get_current_user, AuthenticatedUser
from app.core.config import settings

client = TestClient(app)


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
# 2. Authentication & Authorization Guard Tests
# -----------------------------------------------------------------------------
def test_unauthenticated_access_denied():
    """Attempting to access /api/v1/patients/me without Bearer token must return 401."""
    response = client.get("/api/v1/patients/me")
    assert response.status_code == 401
    assert "detail" in response.json()


def test_missing_credentials_provides_clear_instructions():
    """When DB is unconfigured and invalid token is provided, returns clear setup error or 401."""
    response = client.get(
        "/api/v1/patients/me",
        headers={"Authorization": "Bearer invalid-dummy-token"},
    )
    # Either 401 invalid token or 503 unconfigured service, never a 500 crash or false success
    assert response.status_code in [401, 503]
    detail = response.json().get("detail", "")
    assert len(detail) > 0


# -----------------------------------------------------------------------------
# 3. Duplicate Prevention & Recovery Tests (Mocked Authenticated Session)
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


def test_idempotent_registration_prevents_duplicate_profile(monkeypatch):
    """If authenticated user already has a profile, create_patient_profile returns it idempotently."""
    mock_db = MockSupabaseClient()
    user_id = uuid4()
    patient_id = "MED-2026-TEST01"

    # Seed existing profile for this user
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

    # Override get_current_user dependency
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
        # Verify no second record was created in the table
        assert len(mock_db.table("patient_profiles").data) == 1
    finally:
        app.dependency_overrides.clear()


def test_registration_detects_duplicate_phone_number(monkeypatch):
    """If another user already registered this phone, creation returns 409 Conflict."""
    mock_db = MockSupabaseClient()
    existing_user_id = uuid4()
    new_user_id = uuid4()
    shared_phone = "+919876543210"

    # Seed profile with existing phone hash under another user
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

    # New user with same phone attempts to register
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


def test_account_recovery_rejects_mismatched_challenge(monkeypatch):
    """Account recovery rejects attempts to take over a Patient ID with incorrect challenge info."""
    mock_db = MockSupabaseClient()
    owner_user_id = uuid4()
    attacker_user_id = uuid4()
    target_pid = "MED-2026-VICTIM1"

    # Seed target profile
    mock_db.table("patient_profiles").data.append({
        "id": str(uuid4()),
        "patient_id": target_pid,
        "user_id": str(owner_user_id),
        "phone_hash": hash_phone("+919999999999"),
        "full_name": "Original Patient",
        "date_of_birth": "1980-08-20",
        "gender": "female",
        "emergency_contact_phone": "+918888888888",
        "verification_status": "phone_verified",
        "created_at": "2026-10-19T12:00:00Z",
    })

    monkeypatch.setattr("app.api.v1.patients.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.patients.get_supabase_client", lambda: mock_db)

    # Attacker tries to recover with wrong date of birth
    mock_user = AuthenticatedUser(id=attacker_user_id, phone="+917777777777")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        payload = {
            "target_patient_id": target_pid,
            "challenge_date_of_birth": "1995-01-01",  # Wrong DOB!
        }
        response = client.post("/api/v1/patients/recovery/initiate", json=payload)
        assert response.status_code == 400
        assert "do not match" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
