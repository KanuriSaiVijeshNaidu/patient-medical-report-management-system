import io
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.auth import get_current_user, AuthenticatedUser
from app.core.rate_limit import rate_limiter
from tests.test_patient_auth import MockSupabaseClient

client = TestClient(app)

DUMMY_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
DUMMY_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
DUMMY_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"


@pytest.fixture(autouse=True)
def reset_rate_limits():
    rate_limiter.reset_for_tests()


# -----------------------------------------------------------------------------
# Mock Storage and Database Classes
# -----------------------------------------------------------------------------
class MockStorageBucket:
    def __init__(self):
        self.files = {}

    def upload(self, path, file_bytes, options=None):
        content_type = (options or {}).get("content-type")
        if content_type not in ["application/pdf", "image/jpeg", "image/png"]:
            raise Exception("mime type not supported")
        self.files[path] = file_bytes
        return {"path": path}

    def create_signed_url(self, path, expires_in):
        if path not in self.files and not path.startswith("reports/"):
            raise Exception("Object not found")
        return {"signedURL": f"https://storage.local/{path}?token=mock-signed-token&exp={expires_in}"}

    def remove(self, paths):
        for p in paths:
            self.files.pop(p, None)
        return {"deleted": paths}


class MockReportsQuery:
    def __init__(self, data):
        self.data = data
        self._filters = []
        self._or_clause = None
        self._order_by = []

    def select(self, fields="*"):
        return self

    def eq(self, field, value):
        self._filters.append((field, str(value)))
        return self

    def or_(self, or_clause):
        self._or_clause = or_clause
        return self

    def order(self, column, desc=False):
        self._order_by.append((column, desc))
        return self

    def execute(self):
        filtered = list(self.data)
        for field, val in self._filters:
            filtered = [d for d in filtered if str(d.get(field)) == val]

        if self._or_clause:
            clauses = self._or_clause.split(",")
            def matches_or(item):
                for c in clauses:
                    if ".eq." in c:
                        col, target = c.split(".eq.", 1)
                        if str(item.get(col)) == str(target):
                            return True
                return False
            filtered = [d for d in filtered if matches_or(d)]

        for col, desc in reversed(self._order_by):
            filtered.sort(key=lambda x: str(x.get(col, "")), reverse=desc)

        class Result:
            pass
        res = Result()
        res.data = filtered
        return res


class MockReportsTable:
    def __init__(self, data=None):
        self.data = list(data or [])

    def select(self, fields="*"):
        q = MockReportsQuery(self.data)
        return q.select(fields)

    def eq(self, field, value):
        q = MockReportsQuery(self.data)
        return q.eq(field, value)

    def insert(self, record):
        inserted = dict(record)
        if "id" not in inserted:
            inserted["id"] = str(uuid4())
        if "created_at" not in inserted:
            inserted["created_at"] = datetime.now(timezone.utc).isoformat()
        self.data.append(inserted)
        return self


class MockReportsSupabaseClient(MockSupabaseClient):
    def __init__(self):
        super().__init__()
        self.tables = {
            "users": MockReportsTable(),
            "patient_profiles": MockReportsTable(),
            "patient_recovery_requests": MockReportsTable(),
            "audit_logs": MockReportsTable(),
            "medical_reports": MockReportsTable(),
        }
        self._storage = MockStorageBucket()
        self._storage_fail_mode = False
        self._db_fail_mode = False

    def table(self, table_name):
        if table_name not in self.tables:
            self.tables[table_name] = MockReportsTable()
        return self.tables[table_name]

    def storage_from(self, bucket_name):
        if self._storage_fail_mode:
            raise Exception("Simulated storage cluster outage")
        return self._storage

    @property
    def storage(self):
        class StorageWrapper:
            def __init__(self, outer):
                self.outer = outer
            def from_(self, b_name):
                return self.outer.storage_from(b_name)
        return StorageWrapper(self)

    def rpc(self, func_name, params):
        outer = self

        if func_name == "create_medical_report_atomic":
            class MockCreateRPC:
                def execute(self):
                    if outer._db_fail_mode:
                        raise Exception("Simulated database constraint or connection failure")

                    user_id = params["p_auth_user_id"]
                    p_profiles = [p for p in outer.table("patient_profiles").data if str(p.get("user_id")) == str(user_id)]
                    if not p_profiles:
                        raise Exception("Patient profile not found for authenticated user.")

                    patient_profile_id = str(p_profiles[0]["id"])
                    storage_path = params.get("p_file_storage_path", "")
                    mime_type = params.get("p_mime_type", "")

                    # 1. Database constraint: storage path regex format check (code 23514)
                    import re
                    if not re.match(r"^reports/[0-9a-fA-F-]+/[0-9a-fA-F-]+\.(pdf|jpg|jpeg|png)$", storage_path, re.IGNORECASE):
                        raise Exception("{'message': 'Invalid storage path format.', 'code': '23514'}")

                    # 2. Database constraint: patient directory must match caller profile
                    if not storage_path.lower().startswith(f"reports/{patient_profile_id.lower()}/"):
                        raise Exception("{'message': 'Invalid storage path format: patient directory mismatch.', 'code': '23514'}")

                    # 3. Database constraint: MIME type allowlist check
                    if mime_type not in ("application/pdf", "image/jpeg", "image/png"):
                        raise Exception("{'message': 'Only PDF, JPEG, and PNG documents are permitted for medical reports.', 'code': '23514'}")

                    # 4. Database constraint: extension matches MIME type
                    lower_path = storage_path.lower()
                    if (lower_path.endswith(".pdf") and mime_type != "application/pdf") or \
                       ((lower_path.endswith(".jpg") or lower_path.endswith(".jpeg")) and mime_type != "image/jpeg") or \
                       (lower_path.endswith(".png") and mime_type != "image/png"):
                        raise Exception("{'message': 'MIME type does not match storage path extension.', 'code': '23514'}")

                    report_uuid = str(uuid4())
                    record = {
                        "id": report_uuid,
                        "report_id": params["p_report_id"],
                        "patient_id": patient_profile_id,
                        "upload_source": "patient",
                        "title": params["p_title"],
                        "category": params["p_category"],
                        "report_date": params["p_report_date"],
                        "file_storage_path": storage_path,
                        "file_checksum_sha256": params["p_file_checksum_sha256"],
                        "file_size_bytes": params["p_file_size_bytes"],
                        "mime_type": mime_type,
                        "verification_status": "unverified",
                        "metadata": params.get("p_metadata", {}),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    outer.table("medical_reports").data.append(record)

                    outer.table("audit_logs").data.append({
                        "id": str(uuid4()),
                        "actor_user_id": user_id,
                        "action": "medical_report_uploaded",
                        "entity_type": "medical_report",
                        "entity_id": report_uuid,
                        "details": {
                            "report_id": params["p_report_id"],
                            "category": params["p_category"],
                            "outcome": "success",
                        },
                    })
                    return type("MockResponse", (), {"data": record})()
            return MockCreateRPC()

        elif func_name == "delete_medical_report_atomic":
            class MockDeleteRPC:
                def execute(self):
                    if outer._db_fail_mode:
                        raise Exception("Simulated database constraint or connection failure")

                    user_id = params["p_auth_user_id"]
                    report_id = params["p_report_id"]
                    p_profiles = [p for p in outer.table("patient_profiles").data if str(p.get("user_id")) == str(user_id)]
                    if not p_profiles:
                        raise Exception("no_data_found")

                    patient_profile_id = str(p_profiles[0]["id"])
                    reports = outer.table("medical_reports").data
                    matching = [r for r in reports if str(r["id"]) == str(report_id) and str(r["patient_id"]) == patient_profile_id]
                    if not matching:
                        raise Exception("no_data_found")

                    target = matching[0]
                    reports.remove(target)

                    outer.table("audit_logs").data.append({
                        "id": str(uuid4()),
                        "actor_user_id": user_id,
                        "action": "medical_report_deleted",
                        "entity_type": "medical_report",
                        "entity_id": str(target["id"]),
                        "details": {"report_id": target["report_id"], "outcome": "success"},
                    })
                    return type("MockResponse", (), {"data": {"success": True, "file_storage_path": target["file_storage_path"], "report_id": target["report_id"]}})()
            return MockDeleteRPC()

        return super().rpc(func_name, params)


# -----------------------------------------------------------------------------
# 1. Authentication & Security Edge Cases
# -----------------------------------------------------------------------------
def test_unauthenticated_requests_denied():
    """All reports endpoints reject unauthenticated requests with HTTP 401."""
    res_list = client.get("/api/v1/reports")
    assert res_list.status_code == 401

    res_upload = client.post("/api/v1/reports/upload", data={"title": "Test", "category": "blood_test", "report_date": "2026-01-01"})
    assert res_upload.status_code == 401

    res_details = client.get("/api/v1/reports/REP-2026-TEST01")
    assert res_details.status_code == 401

    res_signed = client.post("/api/v1/reports/REP-2026-TEST01/download-url")
    assert res_signed.status_code == 401

    res_delete = client.delete("/api/v1/reports/REP-2026-TEST01")
    assert res_delete.status_code == 401


# -----------------------------------------------------------------------------
# 2. File Validation: Extension, Magic Bytes, Empty & Oversized Files
# -----------------------------------------------------------------------------
def test_upload_rejects_unsupported_extension(monkeypatch):
    """File without an allowed extension (.pdf, .jpg, .jpeg, .png) is rejected with HTTP 400."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("report.exe", io.BytesIO(DUMMY_PDF_BYTES), "application/pdf")}
        data = {"title": "Blood Test", "category": "blood_test", "report_date": "2026-02-15"}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 400
        assert "unsupported file format" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_mismatched_mime_type(monkeypatch):
    """File claiming text/plain MIME type is rejected with HTTP 400."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("report.pdf", io.BytesIO(DUMMY_PDF_BYTES), "text/plain")}
        data = {"title": "Blood Test", "category": "blood_test", "report_date": "2026-02-15"}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 400
        assert "invalid mime type" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_invalid_magic_bytes(monkeypatch):
    """File named .pdf with application/pdf MIME but invalid header is rejected with HTTP 400."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        # Invalid content starting with executable or text header
        fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00This is not a real PDF document!"
        files = {"file": ("malicious.pdf", io.BytesIO(fake_pdf), "application/pdf")}
        data = {"title": "Lab Results", "category": "blood_test", "report_date": "2026-02-15"}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 400
        assert "invalid file signature" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_valid_png_upload_succeeds(monkeypatch):
    """Uploading a valid PNG photo report succeeds and sets image/png MIME type."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("xray.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")}
        data = {"title": "Chest X-Ray Photo", "category": "xray", "report_date": "2026-02-15"}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 201
        body = res.json()
        assert body["title"] == "Chest X-Ray Photo"
        assert body["category"] == "xray"
        assert body["mime_type"] == "image/png"
        stored_path = list(mock_db._storage.files.keys())[0]
        assert stored_path.startswith(f"reports/{profile_id}/")
        assert stored_path.endswith(".png")
    finally:
        app.dependency_overrides.clear()


def test_valid_jpeg_upload_succeeds(monkeypatch):
    """Uploading a valid JPEG photo report succeeds and sets image/jpeg MIME type."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("scan.jpg", io.BytesIO(DUMMY_JPEG_BYTES), "image/jpeg")}
        data = {"title": "Skin Lesion Photo", "category": "other", "report_date": "2026-02-15"}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 201
        body = res.json()
        assert body["title"] == "Skin Lesion Photo"
        assert body["category"] == "other"
        assert body["mime_type"] == "image/jpeg"
        stored_path = list(mock_db._storage.files.keys())[0]
        assert stored_path.startswith(f"reports/{profile_id}/")
        assert stored_path.endswith(".jpg")
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_empty_file(monkeypatch):
    """0-byte file is rejected with HTTP 400."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
        data = {"title": "Empty Report", "category": "other", "report_date": "2026-02-15"}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 400
        assert "empty (0 bytes)" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_oversized_file(monkeypatch):
    """File exceeding MAX_REPORT_FILE_SIZE_BYTES is rejected with HTTP 413 without unbounded buffering."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    # Set limit to small size (128 KB) for test
    monkeypatch.setattr(settings, "MAX_REPORT_FILE_SIZE_BYTES", 128 * 1024)
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        # Create 200 KB dummy payload starting with %PDF-
        oversized = DUMMY_PDF_BYTES + b"A" * (200 * 1024)
        files = {"file": ("oversized.pdf", io.BytesIO(oversized), "application/pdf")}
        data = {"title": "Large Report", "category": "mri", "report_date": "2026-02-15"}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 413
        assert "exceeds maximum allowed size" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_future_report_date(monkeypatch):
    """Report date in the future is rejected with HTTP 400."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        future_date = (date.today() + timedelta(days=5)).isoformat()
        files = {"file": ("report.pdf", io.BytesIO(DUMMY_PDF_BYTES), "application/pdf")}
        data = {"title": "Future Test", "category": "blood_test", "report_date": future_date}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 400
        assert "future" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 3. Successful Upload & Atomic Audit Log Emission
# -----------------------------------------------------------------------------
def test_valid_pdf_upload_succeeds_with_audit(monkeypatch):
    """Valid PDF upload creates report record, stores file, and logs audit atomically."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("blood_work.pdf", io.BytesIO(DUMMY_PDF_BYTES), "application/pdf")}
        data = {
            "title": "Complete Blood Count",
            "category": "blood_test",
            "report_date": "2026-02-10",
            "description": "Routine annual health check blood panel.",
        }
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 201

        resp_json = res.json()
        assert resp_json["title"] == "Complete Blood Count"
        assert resp_json["category"] == "blood_test"
        assert resp_json["patient_id"] == profile_id
        assert resp_json["report_id"].startswith("REP-2026-")

        # Verify DB record created
        reports = mock_db.table("medical_reports").data
        assert len(reports) == 1
        assert reports[0]["title"] == "Complete Blood Count"

        # Verify storage file created under unpredictable server-side path
        assert len(mock_db._storage.files) == 1
        stored_path = list(mock_db._storage.files.keys())[0]
        assert stored_path.startswith(f"reports/{profile_id}/")
        assert stored_path.endswith(".pdf")

        # Verify audit log record created
        audit_logs = mock_db.table("audit_logs").data
        upload_audits = [a for a in audit_logs if a["action"] == "medical_report_uploaded"]
        assert len(upload_audits) == 1
        assert upload_audits[0]["entity_type"] == "medical_report"
        # Must not log report contents or storage paths
        assert "content" not in upload_audits[0]["details"]
        assert "file_bytes" not in upload_audits[0]["details"]
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. Storage & Database Failure Cleanup (No Orphaned State)
# -----------------------------------------------------------------------------
def test_database_failure_cleans_up_storage_file(monkeypatch):
    """When DB insertion fails after storage upload, orphaned storage file is deleted."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db._db_fail_mode = True  # Trigger simulated DB failure

    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-TEST01",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("test.pdf", io.BytesIO(DUMMY_PDF_BYTES), "application/pdf")}
        data = {"title": "Failed Report", "category": "blood_test", "report_date": "2026-02-10"}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 500

        # Assert no orphaned file remains in storage
        assert len(mock_db._storage.files) == 0

        # Assert no record remains in DB
        assert len(mock_db.table("medical_reports").data) == 0

        # Assert failure event was audited
        fail_audits = [a for a in mock_db.table("audit_logs").data if a["action"] == "medical_report_upload_failed"]
        assert len(fail_audits) == 1
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 5. Cross-Patient Isolation: Patient A Cannot Access Patient B's Report
# -----------------------------------------------------------------------------
def test_cross_patient_isolation(monkeypatch):
    """Patient A cannot list, view, download, or delete Patient B's medical report."""
    user_a = uuid4()
    profile_a = str(uuid4())
    user_b = uuid4()
    profile_b = str(uuid4())

    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.extend([
        {"id": profile_a, "user_id": str(user_a), "patient_id": "MED-2026-AAAAAA"},
        {"id": profile_b, "user_id": str(user_b), "patient_id": "MED-2026-BBBBBB"},
    ])

    report_b_id = str(uuid4())
    report_b_code = "REP-2026-BBBBBB"
    mock_db.table("medical_reports").data.append({
        "id": report_b_id,
        "report_id": report_b_code,
        "patient_id": profile_b,
        "upload_source": "patient",
        "title": "Patient B Private Cardiology Report",
        "category": "other",
        "report_date": "2026-01-20",
        "file_storage_path": f"reports/{profile_b}/doc.pdf",
        "file_checksum_sha256": "0" * 64,
        "file_size_bytes": 1024,
        "mime_type": "application/pdf",
        "verification_status": "unverified",
        "metadata": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mock_db._storage.files[f"reports/{profile_b}/doc.pdf"] = DUMMY_PDF_BYTES

    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)

    # Act as Patient A
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_a, phone="+919876511111")

    try:
        # 1. Listing reports as Patient A returns only Patient A's reports (0 reports)
        res_list = client.get("/api/v1/reports")
        assert res_list.status_code == 200
        assert len(res_list.json()) == 0

        # 2. Querying by Patient B's patient_id returns 404
        res_cross_list = client.get(f"/api/v1/reports/patient/{profile_b}")
        assert res_cross_list.status_code == 404

        # 3. Viewing Patient B's report details returns 404 (does not leak existence)
        res_view = client.get(f"/api/v1/reports/{report_b_code}")
        assert res_view.status_code == 404

        # 4. Requesting signed download URL for Patient B's report returns 404
        res_signed = client.post(f"/api/v1/reports/{report_b_code}/download-url")
        assert res_signed.status_code == 404

        # 5. Deleting Patient B's report returns 404
        res_delete = client.delete(f"/api/v1/reports/{report_b_code}")
        assert res_delete.status_code == 404

        # Verify Patient B's report and storage file are completely intact
        assert len(mock_db.table("medical_reports").data) == 1
        assert f"reports/{profile_b}/doc.pdf" in mock_db._storage.files

        # Verify unauthorized attempts were audited
        denied_audits = [a for a in mock_db.table("audit_logs").data if a["action"] == "medical_report_access_denied"]
        assert len(denied_audits) >= 2
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 6. Signed Download URL Authorization & Non-Disclosure in Logs
# -----------------------------------------------------------------------------
def test_signed_url_generation_for_owner_does_not_log_url(monkeypatch):
    """Owner receives short-lived signed URL, audit log records access without leaking the signed URL."""
    user_id = uuid4()
    profile_id = str(uuid4())
    report_id = str(uuid4())
    report_code = "REP-2026-OWNER1"

    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-OWNER1",
    })
    mock_db.table("medical_reports").data.append({
        "id": report_id,
        "report_id": report_code,
        "patient_id": profile_id,
        "upload_source": "patient",
        "title": "Owner Lab Report",
        "category": "blood_test",
        "report_date": "2026-02-14",
        "file_storage_path": f"reports/{profile_id}/test.pdf",
        "file_checksum_sha256": "a" * 64,
        "file_size_bytes": 2048,
        "mime_type": "application/pdf",
        "verification_status": "unverified",
        "metadata": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mock_db._storage.files[f"reports/{profile_id}/test.pdf"] = DUMMY_PDF_BYTES

    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        res = client.post(f"/api/v1/reports/{report_code}/download-url")
        assert res.status_code == 200
        download_data = res.json()
        assert "download_url" in download_data
        assert "mock-signed-token" in download_data["download_url"]
        assert download_data["expires_in_seconds"] == settings.SIGNED_URL_EXPIRATION_SECONDS

        # Check audit log
        download_audits = [a for a in mock_db.table("audit_logs").data if a["action"] == "medical_report_downloaded"]
        assert len(download_audits) == 1
        # The signed URL and token must NOT be in audit details
        audit_details = download_audits[0]["details"]
        assert "download_url" not in audit_details
        assert "signed_url" not in audit_details
        assert "token" not in audit_details
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 7. Delete Report Endpoint
# -----------------------------------------------------------------------------
def test_delete_report_owner_success(monkeypatch):
    """Owner successfully deletes their report, removing both database record and storage object."""
    user_id = uuid4()
    profile_id = str(uuid4())
    report_id = str(uuid4())
    report_code = "REP-2026-DEL001"
    storage_path = f"reports/{profile_id}/to_delete.pdf"

    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-DEL001",
    })
    mock_db.table("medical_reports").data.append({
        "id": report_id,
        "report_id": report_code,
        "patient_id": profile_id,
        "upload_source": "patient",
        "title": "To Delete Report",
        "category": "other",
        "report_date": "2026-02-14",
        "file_storage_path": storage_path,
        "file_checksum_sha256": "b" * 64,
        "file_size_bytes": 1024,
        "mime_type": "application/pdf",
        "verification_status": "unverified",
        "metadata": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mock_db._storage.files[storage_path] = DUMMY_PDF_BYTES

    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        res = client.delete(f"/api/v1/reports/{report_id}")
        assert res.status_code == 200
        assert res.json()["success"] is True

        # Assert DB record deleted
        assert len(mock_db.table("medical_reports").data) == 0

        # Assert storage file removed
        assert storage_path not in mock_db._storage.files

        # Assert deletion audited
        del_audits = [a for a in mock_db.table("audit_logs").data if a["action"] == "medical_report_deleted"]
        assert len(del_audits) == 1
    finally:
        app.dependency_overrides.clear()


def test_delete_report_storage_failure_gracefully_handled(monkeypatch):
    """When storage file removal fails during report deletion, the deletion still completes
    at the database/audit level and does not crash the client request.
    """
    user_id = uuid4()
    profile_id = str(uuid4())
    report_id = str(uuid4())
    report_code = "REP-2026-DEL002"
    storage_path = f"reports/{profile_id}/{uuid4()}.pdf"

    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-DEL002",
    })
    mock_db.table("medical_reports").data.append({
        "id": report_id,
        "report_id": report_code,
        "patient_id": profile_id,
        "upload_source": "patient",
        "title": "Storage Glitch Report",
        "category": "other",
        "report_date": "2026-02-14",
        "file_storage_path": storage_path,
        "file_checksum_sha256": "c" * 64,
        "file_size_bytes": 1024,
        "mime_type": "application/pdf",
        "verification_status": "unverified",
        "metadata": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mock_db._storage.files[storage_path] = DUMMY_PDF_BYTES

    # Make storage removal raise an exception
    def failing_remove(paths):
        raise Exception("Simulated storage service 503 unavailable")

    mock_db._storage.remove = failing_remove

    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        res = client.delete(f"/api/v1/reports/{report_id}")
        assert res.status_code == 200
        assert res.json()["success"] is True

        # Database record is successfully deleted
        assert len(mock_db.table("medical_reports").data) == 0

        # Deletion audit event is recorded
        del_audits = [a for a in mock_db.table("audit_logs").data if a["action"] == "medical_report_deleted"]
        assert len(del_audits) == 1
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 5. Regression Tests: Storage Paths, Multi-Format (PDF, PNG, JPG, JPEG) & Security
# -----------------------------------------------------------------------------
def test_regression_pdf_upload_persists_metadata_and_correct_storage_path(monkeypatch):
    """Regression: PDF upload persists metadata and exact storage path format."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-REG001",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("blood_test.pdf", io.BytesIO(DUMMY_PDF_BYTES), "application/pdf")}
        data = {
            "title": "Complete Blood Count",
            "category": "blood_test",
            "report_date": "2026-02-10",
            "description": "Routine annual health checkup",
        }
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 201
        report = res.json()
        assert report["title"] == "Complete Blood Count"
        assert report["category"] == "blood_test"
        assert report["mime_type"] == "application/pdf"

        # Verify DB record
        db_reports = mock_db.table("medical_reports").data
        assert len(db_reports) == 1
        rep = db_reports[0]
        assert rep["file_storage_path"].startswith(f"reports/{profile_id}/")
        assert rep["file_storage_path"].endswith(".pdf")
        assert rep["mime_type"] == "application/pdf"
        assert rep["metadata"]["description"] == "Routine annual health checkup"
        assert rep["metadata"]["original_filename"] == "blood_test.pdf"

        # Verify storage file
        assert rep["file_storage_path"] in mock_db._storage.files
    finally:
        app.dependency_overrides.clear()


def test_regression_png_upload_persists_metadata_and_correct_storage_path(monkeypatch):
    """Regression: PNG upload persists metadata and exact storage path format."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-REG002",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("chest_xray.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")}
        data = {
            "title": "Chest X-Ray Scan",
            "category": "xray",
            "report_date": "2026-02-12",
            "description": "Post-recovery clearance scan",
        }
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 201
        report = res.json()
        assert report["title"] == "Chest X-Ray Scan"
        assert report["category"] == "xray"
        assert report["mime_type"] == "image/png"

        db_reports = mock_db.table("medical_reports").data
        assert len(db_reports) == 1
        rep = db_reports[0]
        assert rep["file_storage_path"].startswith(f"reports/{profile_id}/")
        assert rep["file_storage_path"].endswith(".png")
        assert rep["mime_type"] == "image/png"
        assert rep["metadata"]["description"] == "Post-recovery clearance scan"
        assert rep["metadata"]["original_filename"] == "chest_xray.png"

        assert rep["file_storage_path"] in mock_db._storage.files
    finally:
        app.dependency_overrides.clear()


def test_regression_jpg_upload_persists_metadata_and_correct_storage_path(monkeypatch):
    """Regression: JPG photo upload persists metadata and exact storage path format."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-REG003",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("dermatology.jpg", io.BytesIO(DUMMY_JPEG_BYTES), "image/jpeg")}
        data = {
            "title": "Dermatology Lesion Photograph",
            "category": "other",
            "report_date": "2026-02-14",
            "description": "Right forearm lesion evaluation",
        }
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 201
        report = res.json()
        assert report["title"] == "Dermatology Lesion Photograph"
        assert report["category"] == "other"
        assert report["mime_type"] == "image/jpeg"

        db_reports = mock_db.table("medical_reports").data
        assert len(db_reports) == 1
        rep = db_reports[0]
        assert rep["file_storage_path"].startswith(f"reports/{profile_id}/")
        assert rep["file_storage_path"].endswith(".jpg")
        assert rep["mime_type"] == "image/jpeg"
        assert rep["metadata"]["description"] == "Right forearm lesion evaluation"
        assert rep["metadata"]["original_filename"] == "dermatology.jpg"

        assert rep["file_storage_path"] in mock_db._storage.files
    finally:
        app.dependency_overrides.clear()


def test_regression_jpeg_upload_persists_metadata_and_correct_storage_path(monkeypatch):
    """Regression: JPEG photo upload persists metadata and exact storage path format."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-REG004",
    })
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("prescription_scan.jpeg", io.BytesIO(DUMMY_JPEG_BYTES), "image/jpeg")}
        data = {
            "title": "Signed Prescription Slip",
            "category": "prescription",
            "report_date": "2026-02-15",
            "description": "Follow-up prescription from specialist",
        }
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 201
        report = res.json()
        assert report["title"] == "Signed Prescription Slip"
        assert report["category"] == "prescription"
        assert report["mime_type"] == "image/jpeg"

        db_reports = mock_db.table("medical_reports").data
        assert len(db_reports) == 1
        rep = db_reports[0]
        assert rep["file_storage_path"].startswith(f"reports/{profile_id}/")
        assert rep["file_storage_path"].endswith(".jpeg")
        assert rep["mime_type"] == "image/jpeg"
        assert rep["metadata"]["description"] == "Follow-up prescription from specialist"
        assert rep["metadata"]["original_filename"] == "prescription_scan.jpeg"

        assert rep["file_storage_path"] in mock_db._storage.files
    finally:
        app.dependency_overrides.clear()


def test_regression_database_storage_path_constraint_failure_cleans_up_storage(monkeypatch):
    """Regression: When DB rejects path format with 23514, orphaned file is cleaned up."""
    user_id = uuid4()
    profile_id = str(uuid4())
    mock_db = MockReportsSupabaseClient()
    mock_db.table("patient_profiles").data.append({
        "id": profile_id,
        "user_id": str(user_id),
        "patient_id": "MED-2026-REG005",
    })

    # Override RPC to simulate PostgreSQL error 23514 'Invalid storage path format.'
    def failing_rpc(func_name, params):
        class FailingRPC:
            def execute(self):
                raise Exception("{'message': 'Invalid storage path format.', 'code': '23514'}")
        return FailingRPC()

    mock_db.rpc = failing_rpc
    monkeypatch.setattr("app.api.v1.reports.is_db_configured", lambda: True)
    monkeypatch.setattr("app.api.v1.reports.get_supabase_client", lambda: mock_db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, phone="+919876543210")

    try:
        files = {"file": ("report.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")}
        data = {"title": "X-Ray Report", "category": "xray", "report_date": "2026-02-15"}
        res = client.post("/api/v1/reports/upload", files=files, data=data)
        assert res.status_code == 500
        assert "Invalid storage path format" in res.json()["detail"]
        assert "23514" in res.json()["detail"]

        # Crucial security guarantee: orphaned file was cleaned up from storage
        assert len(mock_db._storage.files) == 0
    finally:
        app.dependency_overrides.clear()

