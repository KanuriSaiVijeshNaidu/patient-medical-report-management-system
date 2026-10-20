import hashlib
import io
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.auth import get_current_user, AuthenticatedUser
from app.core.rate_limit import rate_limiter
from tests.test_medical_reports import MockReportsTable, MockStorageBucket
from tests.test_patient_auth import MockSupabaseClient

client = TestClient(app)

DUMMY_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


@pytest.fixture(autouse=True)
def reset_rate_limits():
    rate_limiter.reset_for_tests()


# -----------------------------------------------------------------------------
# Mock Client for Sharing & Access Tests
# -----------------------------------------------------------------------------
class MockShareSupabaseClient(MockSupabaseClient):
    def __init__(self):
        super().__init__()
        self.tables = {
            "users": MockReportsTable(),
            "patient_profiles": MockReportsTable(),
            "medical_reports": MockReportsTable(),
            "record_access_grants": MockReportsTable(),
            "audit_logs": MockReportsTable(),
        }
        self._storage = MockStorageBucket()
        self._db_fail_mode = False

    def table(self, table_name):
        if table_name not in self.tables:
            self.tables[table_name] = MockReportsTable()
        return self.tables[table_name]

    @property
    def storage(self):
        outer = self
        class StorageWrapper:
            def from_(self, b_name):
                return outer._storage
        return StorageWrapper()

    def rpc(self, func_name, params):
        outer = self

        if func_name == "create_report_access_grant_atomic":
            class MockCreateShareRPC:
                def execute(self):
                    if outer._db_fail_mode:
                        raise Exception("Simulated database failure")

                    user_id = params["p_auth_user_id"]
                    report_id = params["p_report_id"]
                    token_hash = params["p_token_hash"]
                    expires_in_sec = params["p_expires_in_seconds"]

                    p_profiles = [p for p in outer.table("patient_profiles").data if str(p.get("user_id")) == str(user_id)]
                    if not p_profiles:
                        raise Exception("insufficient_privilege")

                    patient_profile_id = str(p_profiles[0]["id"])
                    matching_reports = [
                        r for r in outer.table("medical_reports").data
                        if str(r.get("id")) == str(report_id) and str(r.get("patient_id")) == patient_profile_id
                    ]
                    if not matching_reports:
                        raise Exception("insufficient_privilege")

                    target_report = matching_reports[0]
                    grant_uuid = str(uuid4())
                    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_sec)

                    grant_record = {
                        "id": grant_uuid,
                        "patient_id": patient_profile_id,
                        "grant_token_hash": token_hash,
                        "scope": "specific_reports",
                        "report_ids": [report_id],
                        "access_count": 0,
                        "expires_at": expires_at.isoformat(),
                        "is_revoked": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    outer.table("record_access_grants").data.append(grant_record)

                    # Emit audit log atomically
                    outer.table("audit_logs").data.append({
                        "id": str(uuid4()),
                        "actor_user_id": user_id,
                        "action": "report_share_created",
                        "entity_type": "record_access_grant",
                        "entity_id": grant_uuid,
                        "details": {
                            "grant_id": grant_uuid,
                            "report_id": target_report["report_id"],
                            "expires_at": expires_at.isoformat(),
                            "expiry_seconds": expires_in_sec,
                            "outcome": "success",
                        },
                    })

                    return type("MockResponse", (), {"data": {
                        "grant_id": grant_uuid,
                        "report_id": target_report["report_id"],
                        "expires_at": expires_at.isoformat(),
                        "expires_in_seconds": expires_in_sec,
                    }})()
            return MockCreateShareRPC()

        elif func_name == "create_multi_report_access_grant_atomic":
            class MockCreateMultiShareRPC:
                def execute(self):
                    if outer._db_fail_mode:
                        raise Exception("Simulated database failure")

                    user_id = params["p_auth_user_id"]
                    report_ids = params["p_report_ids"]
                    token_hash = params["p_token_hash"]
                    expires_in_sec = params["p_expires_in_seconds"]

                    p_profiles = [p for p in outer.table("patient_profiles").data if str(p.get("user_id")) == str(user_id)]
                    if not p_profiles:
                        raise Exception("insufficient_privilege")

                    patient_profile_id = str(p_profiles[0]["id"])
                    all_reports = outer.table("medical_reports").data
                    matching_reports = []
                    for rid in report_ids:
                        found = [
                            r for r in all_reports
                            if (str(r.get("id")) == str(rid) or str(r.get("report_id")) == str(rid))
                            and str(r.get("patient_id")) == patient_profile_id
                        ]
                        if not found:
                            raise Exception("insufficient_privilege")
                        matching_reports.append(found[0])

                    grant_uuid = str(uuid4())
                    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_sec)
                    report_uuids = [str(r["id"]) for r in matching_reports]
                    report_codes = [r["report_id"] for r in matching_reports]

                    grant_record = {
                        "id": grant_uuid,
                        "patient_id": patient_profile_id,
                        "grant_token_hash": token_hash,
                        "scope": "specific_reports",
                        "report_ids": report_uuids,
                        "access_count": 0,
                        "expires_at": expires_at.isoformat(),
                        "is_revoked": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    outer.table("record_access_grants").data.append(grant_record)

                    # Emit audit log atomically
                    outer.table("audit_logs").data.append({
                        "id": str(uuid4()),
                        "actor_user_id": user_id,
                        "action": "report_share_created",
                        "entity_type": "record_access_grant",
                        "entity_id": grant_uuid,
                        "details": {
                            "grant_id": grant_uuid,
                            "report_ids": report_codes,
                            "reports_count": len(report_codes),
                            "expires_at": expires_at.isoformat(),
                            "expiry_seconds": expires_in_sec,
                            "outcome": "success",
                        },
                    })

                    return type("MockResponse", (), {"data": {
                        "grant_id": grant_uuid,
                        "report_id": report_codes[0],
                        "report_ids": report_codes,
                        "reports_count": len(report_codes),
                        "expires_at": expires_at.isoformat(),
                        "expires_in_seconds": expires_in_sec,
                    }})()
            return MockCreateMultiShareRPC()

        elif func_name == "revoke_report_access_grant_atomic":
            class MockRevokeShareRPC:
                def execute(self):
                    if outer._db_fail_mode:
                        raise Exception("Simulated database failure")

                    user_id = params["p_auth_user_id"]
                    grant_id = params["p_grant_id"]

                    p_profiles = [p for p in outer.table("patient_profiles").data if str(p.get("user_id")) == str(user_id)]
                    if not p_profiles:
                        raise Exception("insufficient_privilege")

                    patient_profile_id = str(p_profiles[0]["id"])
                    grants = outer.table("record_access_grants").data
                    matching = [g for g in grants if str(g.get("id")) == str(grant_id) and str(g.get("patient_id")) == patient_profile_id]
                    if not matching:
                        raise Exception("no_data_found")

                    target_grant = matching[0]
                    target_grant["is_revoked"] = True
                    target_grant["revoked_at"] = datetime.now(timezone.utc).isoformat()

                    # Emit audit log atomically
                    outer.table("audit_logs").data.append({
                        "id": str(uuid4()),
                        "actor_user_id": user_id,
                        "action": "report_share_revoked",
                        "entity_type": "record_access_grant",
                        "entity_id": grant_id,
                        "details": {"grant_id": grant_id, "outcome": "success"},
                    })

                    return type("MockResponse", (), {"data": {
                        "success": True,
                        "grant_id": grant_id,
                        "revoked_at": target_grant["revoked_at"],
                    }})()
            return MockRevokeShareRPC()

        elif func_name == "validate_and_access_shared_report_atomic":
            class MockValidateShareRPC:
                def execute(self):
                    if outer._db_fail_mode:
                        raise Exception("Simulated database failure")

                    token_hash = params["p_token_hash"]
                    grants = outer.table("record_access_grants").data
                    matching = [g for g in grants if str(g.get("grant_token_hash")) == str(token_hash)]
                    if not matching:
                        raise Exception("no_data_found")

                    grant = matching[0]
                    if grant.get("is_revoked"):
                        raise Exception("Share grant has been revoked.")

                    exp_time = datetime.fromisoformat(grant["expires_at"].replace("Z", "+00:00"))
                    if exp_time <= datetime.now(timezone.utc):
                        raise Exception("Share grant has expired.")

                    report_uuid = grant["report_ids"][0]
                    reports = outer.table("medical_reports").data
                    rep_matching = [r for r in reports if str(r.get("id")) == str(report_uuid)]
                    if not rep_matching:
                        raise Exception("no_data_found")

                    report = rep_matching[0]
                    grant["access_count"] = grant.get("access_count", 0) + 1

                    all_matching_reports = [
                        r for r in reports
                        if str(r.get("id")) in [str(ru) for ru in grant["report_ids"]]
                    ]
                    reports_json = [
                        {
                            "id": r["id"],
                            "report_id": r["report_id"],
                            "title": r["title"],
                            "category": r["category"],
                            "report_date": r["report_date"],
                            "file_storage_path": r["file_storage_path"],
                            "file_size_bytes": r["file_size_bytes"],
                            "mime_type": r["mime_type"],
                            "verification_status": r["verification_status"],
                        }
                        for r in all_matching_reports
                    ]

                    # Emit audit log atomically
                    outer.table("audit_logs").data.append({
                        "id": str(uuid4()),
                        "actor_user_id": None,
                        "action": "report_share_accessed",
                        "entity_type": "medical_report",
                        "entity_id": str(report["id"]),
                        "details": {
                            "grant_id": grant["id"],
                            "report_id": report["report_id"],
                            "access_count": grant["access_count"],
                            "outcome": "success",
                        },
                    })

                    return type("MockResponse", (), {"data": {
                        "grant_id": grant["id"],
                        "report_id": report["report_id"],
                        "title": report["title"],
                        "category": report["category"],
                        "report_date": report["report_date"],
                        "file_storage_path": report["file_storage_path"],
                        "file_size_bytes": report["file_size_bytes"],
                        "mime_type": report["mime_type"],
                        "verification_status": report["verification_status"],
                        "share_expires_at": grant["expires_at"],
                        "access_count": grant["access_count"],
                        "reports": reports_json,
                    }})()
            return MockValidateShareRPC()

        return super().rpc(func_name, params)


# -----------------------------------------------------------------------------
# 1. Authentication & Security Edge Cases
# -----------------------------------------------------------------------------
def test_unauthenticated_share_creation_and_revocation_denied():
    """Unauthenticated users cannot create or revoke share grants."""
    res_create = client.post("/api/v1/access/create-share", json={"report_id": str(uuid4())})
    assert res_create.status_code == 401

    res_revoke = client.delete(f"/api/v1/access/revoke/{uuid4()}")
    assert res_revoke.status_code == 401


# -----------------------------------------------------------------------------
# 2. Cross-Patient Isolation: Patient A Cannot Share or Revoke Patient B's Report
# -----------------------------------------------------------------------------
def test_cross_patient_cannot_share_other_patient_report(monkeypatch):
    """Patient A cannot create a share for Patient B's medical report."""
    user_a = uuid4()
    profile_a = str(uuid4())
    user_b = uuid4()
    profile_b = str(uuid4())
    report_b_id = str(uuid4())
    report_b_code = "REP-2026-PATIENTB"

    mock_db = MockShareSupabaseClient()
    mock_db.table("patient_profiles").data.extend([
        {"id": profile_a, "user_id": str(user_a), "patient_id": "MED-2026-AAAA01"},
        {"id": profile_b, "user_id": str(user_b), "patient_id": "MED-2026-BBBB02"},
    ])
    mock_db.table("medical_reports").data.append({
        "id": report_b_id,
        "report_id": report_b_code,
        "patient_id": profile_b,
        "title": "Private Cardiology Report",
        "category": "other",
        "report_date": "2026-02-10",
        "file_storage_path": f"reports/{profile_b}/cardio.pdf",
        "file_size_bytes": 2048,
        "mime_type": "application/pdf",
        "verification_status": "unverified",
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_a, phone="+919876543201")

    try:
        # Patient A attempts to share Patient B's report using UUID
        res = client.post("/api/v1/access/create-share", json={"report_id": report_b_id})
        assert res.status_code == 404

        # Patient A attempts to share Patient B's report using formatted code
        res2 = client.post("/api/v1/access/create-share", json={"report_id": report_b_code})
        assert res2.status_code == 404

        # Verify access denied was audited
        denied_audits = [a for a in mock_db.table("audit_logs").data if a["action"] == "report_share_access_denied"]
        assert len(denied_audits) >= 1
    finally:
        app.dependency_overrides.clear()


def test_cross_patient_cannot_revoke_other_patient_share(monkeypatch):
    """Patient A cannot revoke Patient B's active share grant."""
    user_a = uuid4()
    profile_a = str(uuid4())
    user_b = uuid4()
    profile_b = str(uuid4())
    grant_b_id = str(uuid4())

    mock_db = MockShareSupabaseClient()
    mock_db.table("patient_profiles").data.extend([
        {"id": profile_a, "user_id": str(user_a), "patient_id": "MED-2026-AAAA01"},
        {"id": profile_b, "user_id": str(user_b), "patient_id": "MED-2026-BBBB02"},
    ])
    mock_db.table("record_access_grants").data.append({
        "id": grant_b_id,
        "patient_id": profile_b,
        "grant_token_hash": "a" * 64,
        "scope": "specific_reports",
        "report_ids": [str(uuid4())],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "is_revoked": False,
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_a, phone="+919876543201")

    try:
        res = client.delete(f"/api/v1/access/revoke/{grant_b_id}")
        assert res.status_code == 404

        # Verify grant remains active
        assert mock_db.table("record_access_grants").data[0]["is_revoked"] is False
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 3. High-Entropy Token Generation & Database/Audit Non-Disclosure
# -----------------------------------------------------------------------------
def test_share_creation_never_stores_or_audits_raw_token(monkeypatch):
    """Server generates high-entropy raw token, stores only SHA-256 hash, and keeps raw token out of audit logs."""
    user_id = uuid4()
    profile_id = str(uuid4())
    report_id = str(uuid4())
    report_code = "REP-2026-TEST01"

    mock_db = MockShareSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    mock_db.table("medical_reports").data.append({
        "id": report_id,
        "report_id": report_code,
        "patient_id": profile_id,
        "title": "Complete Blood Count",
        "category": "blood_test",
        "report_date": "2026-02-15",
        "file_storage_path": f"reports/{profile_id}/cbc.pdf",
        "file_size_bytes": 10240,
        "mime_type": "application/pdf",
        "verification_status": "hospital_verified",
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543201")

    try:
        res = client.post("/api/v1/access/create-share", json={
            "report_id": report_code,
            "expires_in_seconds": 900,
        })
        assert res.status_code == 201

        resp_data = res.json()
        assert "raw_token" in resp_data
        raw_token = resp_data["raw_token"]
        assert len(raw_token) >= 32  # High entropy
        assert resp_data["share_url"].endswith(f"/share/{raw_token}")

        # Check Database Record: MUST contain hash, NEVER raw token
        grants = mock_db.table("record_access_grants").data
        assert len(grants) == 1
        stored_grant = grants[0]
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        assert stored_grant["grant_token_hash"] == expected_hash
        assert raw_token not in str(stored_grant)

        # Check Audit Log: MUST NOT contain raw token
        audit_logs = mock_db.table("audit_logs").data
        create_audits = [a for a in audit_logs if a["action"] == "report_share_created"]
        assert len(create_audits) == 1
        audit_details_str = str(create_audits[0]["details"])
        assert raw_token not in audit_details_str
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. Public Recipient Access, Signed URL Generation & Scoped Metadata
# -----------------------------------------------------------------------------
def test_valid_token_access_succeeds_with_short_lived_signed_url(monkeypatch):
    """Valid token allows recipient to access specific report metadata and signed URL."""
    profile_id = str(uuid4())
    report_id = str(uuid4())
    storage_path = f"reports/{profile_id}/scan.pdf"
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    mock_db = MockShareSupabaseClient()
    mock_db.table("medical_reports").data.append({
        "id": report_id,
        "report_id": "REP-2026-MRI001",
        "patient_id": profile_id,
        "title": "Lumbar Spine MRI",
        "category": "mri",
        "report_date": "2026-02-14",
        "file_storage_path": storage_path,
        "file_size_bytes": 1048576,
        "mime_type": "application/pdf",
        "verification_status": "hospital_verified",
    })
    mock_db._storage.files[storage_path] = DUMMY_PDF_BYTES

    mock_db.table("record_access_grants").data.append({
        "id": str(uuid4()),
        "patient_id": profile_id,
        "grant_token_hash": token_hash,
        "scope": "specific_reports",
        "report_ids": [report_id],
        "access_count": 0,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        "is_revoked": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    # Recipient requests access without any authentication header
    res = client.get(f"/api/v1/access/view/{raw_token}")
    assert res.status_code == 200

    view_data = res.json()
    assert view_data["title"] == "Lumbar Spine MRI"
    assert view_data["category"] == "mri"
    assert view_data["verification_status"] == "hospital_verified"
    assert "download_url" in view_data
    assert "mock-signed-token" in view_data["download_url"]

    # Must NOT disclose patient identity, Aadhaar, internal storage path, or user_id
    assert "patient_id" not in view_data
    assert "patient_name" not in view_data
    assert "aadhaar" not in view_data
    assert "file_storage_path" not in view_data

    # Verify access was audited
    access_audits = [a for a in mock_db.table("audit_logs").data if a["action"] == "report_share_accessed"]
    assert len(access_audits) == 1
    assert access_audits[0]["entity_id"] == report_id


# -----------------------------------------------------------------------------
# 5. Invalid, Expired, and Revoked Tokens Fail Safely
# -----------------------------------------------------------------------------
def test_invalid_token_rejected_with_generic_404(monkeypatch):
    """Unknown token returns 404 without leaking state and audits denial."""
    mock_db = MockShareSupabaseClient()
    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    bogus_token = "totally-invalid-and-unknown-token-string"
    res = client.get(f"/api/v1/access/view/{bogus_token}")
    assert res.status_code == 404
    assert "not found, expired, or access has been revoked" in res.json()["detail"].lower()

    denied_audits = [a for a in mock_db.table("audit_logs").data if a["action"] == "report_share_access_denied"]
    assert len(denied_audits) == 1


def test_expired_token_rejected(monkeypatch):
    """Expired token is rejected with 404."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    mock_db = MockShareSupabaseClient()
    mock_db.table("record_access_grants").data.append({
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "grant_token_hash": token_hash,
        "scope": "specific_reports",
        "report_ids": [str(uuid4())],
        "access_count": 0,
        # Expired 10 minutes ago
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        "is_revoked": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    res = client.get(f"/api/v1/access/view/{raw_token}")
    assert res.status_code == 404


def test_revoked_token_rejected(monkeypatch):
    """Revoked token cannot be accessed by recipient."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    mock_db = MockShareSupabaseClient()
    mock_db.table("record_access_grants").data.append({
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "grant_token_hash": token_hash,
        "scope": "specific_reports",
        "report_ids": [str(uuid4())],
        "access_count": 0,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        "is_revoked": True,  # Revoked
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    res = client.get(f"/api/v1/access/view/{raw_token}")
    assert res.status_code == 404


# -----------------------------------------------------------------------------
# 6. Immediate Revocation Prevents Subsequent Access
# -----------------------------------------------------------------------------
def test_revocation_lifecycle_prevents_subsequent_access(monkeypatch):
    """Patient revokes an active share grant, successfully blocking future recipient access."""
    user_id = uuid4()
    profile_id = str(uuid4())
    report_id = str(uuid4())
    grant_id = str(uuid4())
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    storage_path = f"reports/{profile_id}/test.pdf"

    mock_db = MockShareSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    mock_db.table("medical_reports").data.append({
        "id": report_id,
        "report_id": "REP-2026-TEST01",
        "patient_id": profile_id,
        "title": "Blood Test",
        "category": "blood_test",
        "report_date": "2026-02-15",
        "file_storage_path": storage_path,
        "file_size_bytes": 1024,
        "mime_type": "application/pdf",
        "verification_status": "unverified",
    })
    mock_db._storage.files[storage_path] = DUMMY_PDF_BYTES

    mock_db.table("record_access_grants").data.append({
        "id": grant_id,
        "patient_id": profile_id,
        "grant_token_hash": token_hash,
        "scope": "specific_reports",
        "report_ids": [report_id],
        "access_count": 0,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        "is_revoked": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    # 1. Recipient can access report initially
    res_before = client.get(f"/api/v1/access/view/{raw_token}")
    assert res_before.status_code == 200

    # 2. Owner revokes the grant
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543201")
    try:
        res_revoke = client.delete(f"/api/v1/access/revoke/{grant_id}")
        assert res_revoke.status_code == 200
        assert res_revoke.json()["success"] is True
    finally:
        app.dependency_overrides.clear()

    # 3. Subsequent recipient access fails immediately with 404
    res_after = client.get(f"/api/v1/access/view/{raw_token}")
    assert res_after.status_code == 404


# -----------------------------------------------------------------------------
# 7. Token Guessing Rate Limiting
# -----------------------------------------------------------------------------
def test_token_guessing_is_rate_limited(monkeypatch):
    """Rapid recipient token guessing attempts trigger rate limiting (HTTP 429)."""
    mock_db = MockShareSupabaseClient()
    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    # Exhaust rate limit of 30 requests per minute
    for _ in range(30):
        res = client.get("/api/v1/access/view/random-token-attempt-string")
        assert res.status_code in [404, 429]

    # 31st request must trigger 429
    res_blocked = client.get("/api/v1/access/view/random-token-attempt-string")
    assert res_blocked.status_code == 429
    assert "rate limit exceeded" in res_blocked.json()["detail"].lower()


# -----------------------------------------------------------------------------
# 8. Security Headers & Sensitive Response Protection (Phase 3C Validation)
# -----------------------------------------------------------------------------
def test_security_headers_and_cache_control_on_recipient_view(monkeypatch):
    """Verifies that recipient endpoint emits Cache-Control: no-store, Referrer-Policy: no-referrer,
    X-Frame-Options: DENY, and X-Content-Type-Options: nosniff.
    """
    mock_db = MockShareSupabaseClient()
    user_id = uuid4()
    profile_id = str(uuid4())
    report_id = str(uuid4())
    grant_id = str(uuid4())
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    storage_path = f"reports/{profile_id}/{uuid4()}.pdf"

    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "PID-20261019-1234",
    })
    mock_db.table("medical_reports").data.append({
        "id": report_id,
        "report_id": "REP-20261020-001",
        "patient_id": profile_id,
        "title": "Confidential Blood Test",
        "category": "blood_test",
        "report_date": "2026-10-19",
        "file_storage_path": storage_path,
        "file_size_bytes": len(DUMMY_PDF_BYTES),
        "mime_type": "application/pdf",
        "verification_status": "unverified",
    })
    mock_db._storage.files[storage_path] = DUMMY_PDF_BYTES
    mock_db.table("record_access_grants").data.append({
        "id": grant_id,
        "patient_id": profile_id,
        "grant_token_hash": token_hash,
        "scope": "specific_reports",
        "report_ids": [report_id],
        "access_count": 0,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        "is_revoked": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    res = client.get(f"/api/v1/access/view/{raw_token}")
    assert res.status_code == 200

    # Strict Cache-Control verification
    cache_control = res.headers.get("Cache-Control", "")
    assert "no-store" in cache_control
    assert "no-cache" in cache_control

    # Restrictive Referrer-Policy verification
    assert res.headers.get("Referrer-Policy") == "no-referrer"

    # Frame protection and MIME sniffing defense
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-Content-Type-Options") == "nosniff"


def test_invalid_and_expired_tokens_never_leak_signed_urls_or_metadata(monkeypatch):
    """Ensures that invalid, expired, or non-existent tokens return generic 404 and never
    disclose report metadata, filenames, signed URLs, or patient identifiers.
    """
    mock_db = MockShareSupabaseClient()
    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    # 1. Non-existent token
    res_fake = client.get(f"/api/v1/access/view/{secrets.token_urlsafe(32)}")
    assert res_fake.status_code == 404
    body = res_fake.json()
    assert "download_url" not in body
    assert "file_storage_path" not in body
    assert "patient_id" not in body
    assert "report_id" not in body
    assert body["detail"] == "Shared medical report not found, expired, or access has been revoked."

    # 2. Security headers are maintained even on 404 responses
    assert "no-store" in res_fake.headers.get("Cache-Control", "")
    assert res_fake.headers.get("Referrer-Policy") == "no-referrer"


# -----------------------------------------------------------------------------
# Multi-Report QR Sharing Tests
# -----------------------------------------------------------------------------
def test_multi_report_share_creation_and_doctor_access(monkeypatch):
    """Verifies that a patient can bundle multiple medical reports into a single QR grant,
    and a doctor viewing the share link receives all authorized reports with individual download URLs.
    """
    mock_db = MockShareSupabaseClient()
    user_id = str(uuid4())
    profile_id = str(uuid4())

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=UUID(user_id), email="patient_multi@test.com", role="patient"
    )

    mock_db.table("users").data.append({"id": user_id, "role": "patient"})
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": user_id,
        "patient_id": "MED-2026-MULTI",
        "full_name": "Multi Report Patient",
    })

    # Add 3 reports: 2 will be shared, 1 will remain unshared
    rep1_id = str(uuid4())
    rep1_path = f"{profile_id}/rep1.pdf"
    mock_db.table("medical_reports").data.append({
        "id": rep1_id,
        "report_id": "REP-2026-REP001",
        "patient_id": profile_id,
        "title": "Complete Blood Count",
        "category": "blood_test",
        "report_date": "2026-10-15",
        "file_storage_path": rep1_path,
        "file_size_bytes": 1024,
        "mime_type": "application/pdf",
        "verification_status": "hospital_verified",
    })
    mock_db._storage.files[rep1_path] = DUMMY_PDF_BYTES

    rep2_id = str(uuid4())
    rep2_path = f"{profile_id}/rep2.pdf"
    mock_db.table("medical_reports").data.append({
        "id": rep2_id,
        "report_id": "REP-2026-REP002",
        "patient_id": profile_id,
        "title": "Chest X-Ray Digital",
        "category": "xray",
        "report_date": "2026-10-18",
        "file_storage_path": rep2_path,
        "file_size_bytes": 2048,
        "mime_type": "application/pdf",
        "verification_status": "patient_uploaded",
    })
    mock_db._storage.files[rep2_path] = DUMMY_PDF_BYTES

    rep3_id = str(uuid4())
    rep3_path = f"{profile_id}/rep3.pdf"
    mock_db.table("medical_reports").data.append({
        "id": rep3_id,
        "report_id": "REP-2026-REP003",
        "patient_id": profile_id,
        "title": "Unshared Brain MRI",
        "category": "mri",
        "report_date": "2026-10-19",
        "file_storage_path": rep3_path,
        "file_size_bytes": 4096,
        "mime_type": "application/pdf",
        "verification_status": "hospital_verified",
    })
    mock_db._storage.files[rep3_path] = DUMMY_PDF_BYTES

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    # 1. Create multi-report share for rep1 and rep2
    create_res = client.post("/api/v1/access/create-share", json={
        "report_ids": [rep1_id, rep2_id],
        "expires_in_seconds": 1800,
    })
    assert create_res.status_code == 201, create_res.text
    grant_body = create_res.json()
    assert grant_body["reports_count"] == 2
    assert "REP-2026-REP001" in grant_body["report_ids"]
    assert "REP-2026-REP002" in grant_body["report_ids"]
    raw_token = grant_body["raw_token"]

    # 2. Doctor views shared session via raw_token
    view_res = client.get(f"/api/v1/access/view/{raw_token}")
    assert view_res.status_code == 200, view_res.text
    view_body = view_res.json()

    # Verify both reports are returned in the reports array
    assert "reports" in view_body
    shared_reports = view_body["reports"]
    assert len(shared_reports) == 2

    report_codes_received = [r["report_id"] for r in shared_reports]
    assert "REP-2026-REP001" in report_codes_received
    assert "REP-2026-REP002" in report_codes_received
    assert "REP-2026-REP003" not in report_codes_received  # Unshared report must NEVER leak!

    # Verify each report has an authorized download URL and metadata
    for rep_item in shared_reports:
        assert rep_item["download_url"].startswith("http")
        assert "expires_in_seconds" in rep_item or "download_url_expires_in_seconds" in rep_item
        assert rep_item["verification_status"] in ["hospital_verified", "patient_uploaded"]

    # Verify top-level backward compatibility fields are also populated
    assert view_body["report_id"] in ["REP-2026-REP001", "REP-2026-REP002"]
    assert view_body["download_url"].startswith("http")

    app.dependency_overrides.clear()


def test_multi_report_share_rejects_unowned_report(monkeypatch):
    """Verifies that an attempt to include a report owned by another patient fails immediately,
    auditing a security access denied event and refusing grant creation.
    """
    mock_db = MockShareSupabaseClient()
    user_id = str(uuid4())
    profile_id = str(uuid4())
    other_profile_id = str(uuid4())

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=UUID(user_id), email="attacker@test.com", role="patient"
    )

    mock_db.table("users").data.append({"id": user_id, "role": "patient"})
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": user_id,
        "patient_id": "MED-2026-ATTACKER",
        "full_name": "Attacker Patient",
    })

    # Legitimate report owned by user
    own_rep_id = str(uuid4())
    mock_db.table("medical_reports").data.append({
        "id": own_rep_id,
        "report_id": "REP-2026-OWN001",
        "patient_id": profile_id,
        "title": "Own Blood Test",
        "category": "blood_test",
        "report_date": "2026-10-15",
        "file_storage_path": f"{profile_id}/own.pdf",
        "file_size_bytes": 1024,
        "mime_type": "application/pdf",
        "verification_status": "hospital_verified",
    })

    # Victim report owned by another patient
    victim_rep_id = str(uuid4())
    mock_db.table("medical_reports").data.append({
        "id": victim_rep_id,
        "report_id": "REP-2026-VICTIM001",
        "patient_id": other_profile_id,
        "title": "Victim Confidential Biopsy",
        "category": "other",
        "report_date": "2026-10-16",
        "file_storage_path": f"{other_profile_id}/victim.pdf",
        "file_size_bytes": 2048,
        "mime_type": "application/pdf",
        "verification_status": "hospital_verified",
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    # Attempt to bundle own report + victim report
    res = client.post("/api/v1/access/create-share", json={
        "report_ids": [own_rep_id, victim_rep_id],
        "expires_in_seconds": 900,
    })
    assert res.status_code in [403, 404]

    # Verify no grant was created
    assert len(mock_db.table("record_access_grants").data) == 0

    # Verify security audit event logged
    audit_logs = mock_db.table("audit_logs").data
    denied_events = [a for a in audit_logs if a.get("action") == "report_share_access_denied"]
    assert len(denied_events) >= 1

    app.dependency_overrides.clear()


def test_multi_report_share_rejects_empty_selection(monkeypatch):
    """Verifies that submitting an empty report_ids list returns HTTP 400 Bad Request."""
    mock_db = MockShareSupabaseClient()
    user_id = str(uuid4())
    profile_id = str(uuid4())

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=UUID(user_id), email="patient@test.com", role="patient"
    )

    mock_db.table("users").data.append({"id": user_id, "role": "patient"})
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": user_id,
        "patient_id": "MED-2026-EMPTY",
        "full_name": "Empty Patient",
    })

    monkeypatch.setattr("app.api.v1.access.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.access.get_supabase_client", lambda: mock_db)

    res = client.post("/api/v1/access/create-share", json={
        "report_ids": [],
        "expires_in_seconds": 900,
    })
    assert res.status_code == 400
    assert "At least one medical report must be selected" in res.json()["detail"]

    app.dependency_overrides.clear()

