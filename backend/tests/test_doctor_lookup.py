"""Test suite for Doctor Patient Lookup and Hospital Authorization.

Verifies:
1. Hospital staff authentication (valid vs invalid credentials).
2. Authorized doctor lookup returns patient identity details and authorized medical reports with signed URLs.
3. Strict hospital authorization: knowing Patient ID does NOT grant access without an active grant.
4. Unauthorized doctor lookup returns 403 Forbidden with zero report leakage.
5. Non-existent Patient ID returns 404 Not Found.
6. Unauthenticated requests return 401 Unauthorized.
7. Patient role token attempting hospital lookup is rejected with 403 Forbidden.
8. Report download URL endpoint strictly enforces institutional authorization.
"""
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import create_access_token

client = TestClient(app)

TEST_PATIENT_ID = "MED-2026-3N62YU"


@pytest.fixture(scope="module")
def authorized_doctor_token():
    """Returns access token for Dr. Ananya Sharma at City General Hospital (Authorized)."""
    login_res = client.post("/api/v1/hospital/login", json={
        "email": "dr.sharma@cityhospital.org",
        "password": "Password123!",
        "hospital_registration_number": "HOSP-REG-4421"
    })
    assert login_res.status_code == 200, f"Dr. Sharma login failed: {login_res.text}"
    return login_res.json()["access_token"]


@pytest.fixture(scope="module")
def unauthorized_doctor_token():
    """Returns access token for Dr. Rajesh Patel at Metro Specialty Clinic (Unauthorized)."""
    login_res = client.post("/api/v1/hospital/login", json={
        "email": "dr.patel@metroclinic.org",
        "password": "Password123!",
        "hospital_registration_number": "HOSP-REG-9999"
    })
    assert login_res.status_code == 200, f"Dr. Patel login failed: {login_res.text}"
    return login_res.json()["access_token"]


@pytest.fixture(scope="module")
def patient_role_token():
    """Returns an access token with role='patient' to test role separation."""
    return create_access_token(user_id=uuid4(), role="patient", username="testpatient")


# -----------------------------------------------------------------------------
# Hospital Staff Authentication Tests
# -----------------------------------------------------------------------------
def test_hospital_staff_login_success():
    response = client.post("/api/v1/hospital/login", json={
        "email": "dr.sharma@cityhospital.org",
        "password": "Password123!",
        "hospital_registration_number": "HOSP-REG-4421"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["hospital_name"] == "City General Hospital"
    assert data["hospital_registration_number"] == "HOSP-REG-4421"
    assert data["staff_role"] == "clinician"


def test_hospital_staff_login_invalid_password():
    response = client.post("/api/v1/hospital/login", json={
        "email": "dr.sharma@cityhospital.org",
        "password": "WrongPassword999!",
        "hospital_registration_number": "HOSP-REG-4421"
    })
    assert response.status_code == 401


def test_hospital_staff_login_unregistered_hospital():
    response = client.post("/api/v1/hospital/login", json={
        "email": "dr.sharma@cityhospital.org",
        "password": "Password123!",
        "hospital_registration_number": "HOSP-NONEXISTENT-999"
    })
    assert response.status_code == 401


# -----------------------------------------------------------------------------
# Doctor Patient Lookup Tests
# -----------------------------------------------------------------------------
def test_authorized_doctor_lookup_success(authorized_doctor_token):
    """Authorized doctor retrieves patient identity confirmation and available reports."""
    response = client.get(
        f"/api/v1/hospital/patient/{TEST_PATIENT_ID}",
        headers={"Authorization": f"Bearer {authorized_doctor_token}"}
    )
    assert response.status_code == 200
    data = response.json()

    assert data["authorized"] is True
    assert data["hospital_name"] == "City General Hospital"

    # Verify patient identity details
    patient = data["patient"]
    assert patient["patient_id"] == TEST_PATIENT_ID
    assert patient["full_name"] == "k sai vijesh"
    assert patient["gender"] == "male"
    assert patient["blood_group"] is not None

    # Verify reports list
    reports = data["reports"]
    assert isinstance(reports, list)
    assert len(reports) >= 1

    for r in reports:
        assert "report_id" in r
        assert "title" in r
        assert "category" in r
        assert "report_date" in r
        assert "download_url" in r
        assert r["download_url"].startswith("http")
        assert r["download_url_expires_in_seconds"] == 300


def test_unauthorized_doctor_lookup_blocked(unauthorized_doctor_token):
    """Doctor from an unauthorized hospital organization receives 403 Forbidden with zero report leakage."""
    response = client.get(
        f"/api/v1/hospital/patient/{TEST_PATIENT_ID}",
        headers={"Authorization": f"Bearer {unauthorized_doctor_token}"}
    )
    assert response.status_code == 403
    data = response.json()
    assert "detail" in data
    assert "not authorized" in data["detail"].lower()
    # Confirm zero report metadata or data leaked
    assert "reports" not in data
    assert "patient" not in data


def test_nonexistent_patient_lookup_returns_404(authorized_doctor_token):
    """Looking up a valid-format but non-existent Patient ID returns 404."""
    response = client.get(
        "/api/v1/hospital/patient/MED-9999-NOTFOUND",
        headers={"Authorization": f"Bearer {authorized_doctor_token}"}
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_invalid_patient_id_format_returns_404(authorized_doctor_token):
    """Looking up an invalid ID format returns 404."""
    response = client.get(
        "/api/v1/hospital/patient/INVALID-PATIENT-ID",
        headers={"Authorization": f"Bearer {authorized_doctor_token}"}
    )
    assert response.status_code == 404


def test_unauthenticated_request_returns_401():
    """Requests without Bearer token are rejected."""
    response = client.get(f"/api/v1/hospital/patient/{TEST_PATIENT_ID}")
    assert response.status_code == 401


def test_patient_role_token_blocked_from_hospital_lookup(patient_role_token):
    """Users with role='patient' cannot access hospital doctor lookup endpoint."""
    response = client.get(
        f"/api/v1/hospital/patient/{TEST_PATIENT_ID}",
        headers={"Authorization": f"Bearer {patient_role_token}"}
    )
    assert response.status_code == 403
    assert "restricted to authorized hospital" in response.json()["detail"].lower()


# -----------------------------------------------------------------------------
# Report Download URL Authorization Tests
# -----------------------------------------------------------------------------
def test_report_download_url_authorization(authorized_doctor_token, unauthorized_doctor_token):
    """Authorized doctor can obtain download URL; unauthorized doctor is blocked."""
    # 1. Fetch authorized report ID
    lookup_res = client.get(
        f"/api/v1/hospital/patient/{TEST_PATIENT_ID}",
        headers={"Authorization": f"Bearer {authorized_doctor_token}"}
    )
    assert lookup_res.status_code == 200
    report_id = lookup_res.json()["reports"][0]["report_id"]

    # 2. Authorized doctor can refresh download URL
    download_res = client.get(
        f"/api/v1/hospital/reports/{report_id}/download-url",
        headers={"Authorization": f"Bearer {authorized_doctor_token}"}
    )
    assert download_res.status_code == 200
    assert "download_url" in download_res.json()
    assert download_res.json()["download_url"].startswith("http")

    # 3. Unauthorized doctor is blocked from generating download URL
    unauth_download_res = client.get(
        f"/api/v1/hospital/reports/{report_id}/download-url",
        headers={"Authorization": f"Bearer {unauthorized_doctor_token}"}
    )
    assert unauth_download_res.status_code == 403
    assert "not authorized" in unauth_download_res.json()["detail"].lower()
