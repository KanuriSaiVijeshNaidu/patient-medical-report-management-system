import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.core.config import settings
from app.core.database import get_supabase_client, create_isolated_auth_client
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.security import create_access_token, verify_password, hash_password
from app.core.audit import audit_service
from app.models.schemas import (
    HospitalStaffLoginRequest,
    HospitalStaffLoginResponse,
    DoctorPatientInfo,
    DoctorPatientLookupResponse,
    SharedReportItem,
    GrantHospitalAccessRequest,
    GrantHospitalAccessResponse,
)

logger = logging.getLogger("api.hospital")
router = APIRouter()

DEMO_STAFF_ACCOUNTS = {
    "dr.sharma@cityhospital.org": {
        "hospital_reg": "HOSP-REG-4421",
        "hospital_id": "33333333-3333-3333-3333-333333333333",
        "name": "Dr. Ananya Sharma",
        "employee_id": "EMP-CGH-101",
        "role": "clinician",
        "department": "Internal Medicine",
        "reg_no": "MCI-2018-98421",
        "password": "Password123!",
    },
    "doctor@cityhospital.org": {
        "hospital_reg": "HOSP-REG-4421",
        "hospital_id": "33333333-3333-3333-3333-333333333333",
        "name": "Dr. Staff Clinician",
        "employee_id": "EMP-CGH-102",
        "role": "clinician",
        "department": "General Medicine",
        "reg_no": "MCI-2019-12345",
        "password": "StaffPassword123!",
    },
    "dr.patel@metroclinic.org": {
        "hospital_reg": "HOSP-REG-9999",
        "hospital_id": "44444444-4444-4444-4444-444444444444",
        "name": "Dr. Rajesh Patel",
        "employee_id": "EMP-MSC-502",
        "role": "clinician",
        "department": "Cardiology",
        "reg_no": "MCI-2015-77319",
        "password": "Password123!",
    },
}


def _ensure_staff_record(client, email: str) -> Optional[dict]:
    """Ensures demo doctor accounts exist in auth.users, public.users, and public.hospital_staff."""
    if email not in DEMO_STAFF_ACCOUNTS:
        return None
    demo_info = DEMO_STAFF_ACCOUNTS[email]
    try:
        user_id = None
        all_users = client.auth.admin.list_users()
        matched = [u for u in all_users if getattr(u, "email", None) == email]
        if matched:
            user_id = matched[0].id
        else:
            u = client.auth.admin.create_user({
                "email": email,
                "password": demo_info["password"],
                "email_confirm": True,
                "user_metadata": {"full_name": demo_info["name"], "role": "hospital_staff"},
            })
            user_id = u.user.id

        client.table("users").upsert({
            "id": user_id,
            "email": email,
            "role": "hospital_staff",
            "is_active": True,
        }).execute()

        staff_res = client.table("hospital_staff").select("*").eq("user_id", user_id).execute()
        if staff_res.data:
            return staff_res.data[0]

        new_staff = client.table("hospital_staff").insert({
            "user_id": user_id,
            "hospital_id": demo_info["hospital_id"],
            "employee_id": demo_info["employee_id"],
            "role": demo_info["role"],
            "department": demo_info["department"],
            "clinical_registration_number": demo_info["reg_no"],
            "is_active": True,
        }).execute()
        if new_staff.data:
            return new_staff.data[0]
    except Exception as e:
        logger.warning("Error ensuring staff record for %s: %s", email, e)
    return None


@router.post(
    "/login",
    response_model=HospitalStaffLoginResponse,
    summary="Hospital staff authentication with organization verification",
)
def staff_login(payload: HospitalStaffLoginRequest, request: Request):
    """Authenticates hospital clinicians and staff, verifying institutional affiliation."""
    clean_email = payload.email.strip().lower()
    clean_reg = (payload.hospital_registration_number or "HOSP-REG-4421").strip().upper()
    client = get_supabase_client()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable.",
        )

    # 1. Verify hospital organization is active and verified
    hosp_res = client.table("hospitals").select("*").eq("registration_number", clean_reg).execute()
    if not hosp_res.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Hospital organization '{clean_reg}' not found.",
        )

    hospital = hosp_res.data[0]
    if not hospital.get("is_active") or hospital.get("verification_status") != "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hospital organization is inactive or unverified.",
        )

    # 2. Look up or provision staff record
    staff = None
    user_res = client.table("users").select("id, email, is_active, role").ilike("email", clean_email).execute()
    if not user_res.data:
        staff = _ensure_staff_record(client, clean_email)
        user_res = client.table("users").select("id, email, is_active, role").ilike("email", clean_email).execute()

    if not user_res.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Staff account not found.",
        )

    user = user_res.data[0]
    user_id = user["id"]

    # 3. Check staff membership in this hospital
    if not staff:
        staff_res = client.table("hospital_staff").select("*").eq("user_id", user_id).eq("is_active", True).execute()
        if not staff_res.data:
            staff = _ensure_staff_record(client, clean_email)
            staff_res = client.table("hospital_staff").select("*").eq("user_id", user_id).eq("is_active", True).execute()

        if not staff_res.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not registered as active hospital staff.",
            )
        staff = staff_res.data[0]

    if str(staff.get("hospital_id")) != str(hospital["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff member does not belong to the selected hospital organization.",
        )

    # 4. Verify password
    # Support demo accounts or Supabase Auth password verification
    is_valid_pw = False
    if clean_email in DEMO_STAFF_ACCOUNTS:
        if payload.password == DEMO_STAFF_ACCOUNTS[clean_email]["password"]:
            is_valid_pw = True

    if not is_valid_pw:
        try:
            auth_client = create_isolated_auth_client()
            if auth_client:
                auth_res = auth_client.auth.sign_in_with_password({
                    "email": clean_email,
                    "password": payload.password,
                })
                if auth_res and auth_res.user:
                    is_valid_pw = True
        except Exception:
            pass

    if not is_valid_pw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # 5. Issue JWT with role='hospital_staff'
    staff_name = DEMO_STAFF_ACCOUNTS.get(clean_email, {}).get("name") or clean_email.split("@")[0].replace(".", " ").title()
    token = create_access_token(
        user_id=UUID(user_id),
        role="hospital_staff",
        username=clean_email,
        expires_delta=timedelta(hours=12),
    )

    logger.info("Hospital staff %s logged in successfully for %s", clean_email, hospital["name"])

    return HospitalStaffLoginResponse(
        access_token=token,
        token_type="bearer",
        staff_id=UUID(staff["id"]),
        staff_name=staff_name,
        staff_role=staff.get("role", "clinician"),
        employee_id=staff.get("employee_id", "EMP-001"),
        hospital_id=UUID(hospital["id"]),
        hospital_name=hospital["name"],
        hospital_registration_number=hospital["registration_number"],
    )


@router.get(
    "/patient/{patient_id_code}",
    response_model=DoctorPatientLookupResponse,
    summary="Doctor Patient Lookup by unique Patient ID",
)
def doctor_lookup_patient(
    patient_id_code: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieves patient identity and authorized medical reports using the permanent Patient ID.

    Strictly enforces hospital authorization:
    - Verifies caller is active hospital staff.
    - Requires active patient-to-hospital access grant OR reports issued by this hospital.
    - If unauthorized, returns HTTP 403 Forbidden with ZERO report leakage and emits an audit event.
    - Generates short-lived (300s) signed URLs for authorized reports.
    """
    # 1. Enforce hospital staff role
    if current_user.role not in ["hospital_staff", "clinician", "doctor", "admin", "platform_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to authorized hospital clinicians and staff.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable.",
        )

    # 2. Normalize and validate Patient ID format
    clean_patient_id = patient_id_code.strip().upper()
    if not re.match(r"^MED-\d{4}-[A-Z0-9]{4,10}$", clean_patient_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient profile not found for Patient ID: {clean_patient_id}",
        )

    client_ip = request.client.host if request.client else "127.0.0.1"
    request_id = getattr(request.state, "request_id", None) or "req-doctor-lookup"

    # 3. Call atomic RPC doctor_lookup_patient_reports_atomic
    try:
        rpc_res = client.rpc("doctor_lookup_patient_reports_atomic", {
            "p_staff_user_id": str(current_user.id),
            "p_patient_id_code": clean_patient_id,
            "p_ip_address": client_ip,
            "p_request_id": request_id,
        }).execute()
    except Exception as exc:
        err_msg = str(exc)
        logger.warning("doctor_lookup_patient_reports_atomic RPC error: %s", err_msg)
        if "no_data_found" in err_msg or "not found" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient profile not found for Patient ID: {clean_patient_id}",
            )
        if "insufficient_privilege" in err_msg or "42501" in err_msg or "not authorized" in err_msg.lower():
            # Emit persistent security audit event for denied attempt
            audit_service.log_security_event(
                client=client,
                action="medical_report_access_denied",
                entity_type="patient_profile",
                entity_id=clean_patient_id,
                ip_address=client_ip,
                actor_user_id=current_user.id,
                details={
                    "patient_id": clean_patient_id,
                    "reason": "unauthorized_hospital_lookup_no_active_grant",
                    "request_id": request_id,
                    "outcome": "denied",
                },
                request_id=request_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Your hospital organization is not authorized to view records for Patient ID: {clean_patient_id}. An active institutional access grant is required.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve patient medical records.",
        )

    data = rpc_res.data
    if not data or not data.get("authorized"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for Patient ID: {clean_patient_id}.",
        )

    # 4. Generate signed URLs for each authorized report
    raw_reports = data.get("reports") or []
    shared_reports: List[SharedReportItem] = []
    bucket_name = settings.STORAGE_BUCKET_NAME

    for r in raw_reports:
        file_storage_path = r.get("file_storage_path")
        signed_url = ""
        if file_storage_path:
            try:
                signed_res = client.storage.from_(bucket_name).create_signed_url(file_storage_path, 300)
                signed_url = signed_res.get("signedURL") or signed_res.get("signedUrl") or ""
            except Exception as st_err:
                logger.warning("Could not create signed URL for %s: %s", file_storage_path, st_err)

        shared_reports.append(
            SharedReportItem(
                report_id=r.get("report_id"),
                title=r.get("title"),
                category=r.get("category"),
                report_date=r.get("report_date"),
                file_size_bytes=r.get("file_size_bytes", 0),
                mime_type=r.get("mime_type", "application/pdf"),
                verification_status=r.get("verification_status", "unverified"),
                download_url=signed_url,
                download_url_expires_in_seconds=300,
            )
        )

    return DoctorPatientLookupResponse(
        authorized=True,
        patient=DoctorPatientInfo(**data["patient"]),
        hospital_name=data["hospital_name"],
        hospital_id=UUID(data["hospital_id"]),
        reports=shared_reports,
    )


@router.get(
    "/reports/{report_id}/download-url",
    summary="Generate fresh signed download URL for an authorized hospital clinician",
)
def get_hospital_report_download_url(
    report_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Generates a fresh short-lived signed URL for an authorized clinician."""
    if current_user.role not in ["hospital_staff", "clinician", "doctor", "admin", "platform_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to authorized hospital personnel.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable.",
        )

    # 1. Fetch staff member's hospital_id
    staff_res = client.table("hospital_staff").select("hospital_id, is_active").eq("user_id", str(current_user.id)).execute()
    if not staff_res.data or not staff_res.data[0].get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active hospital staff registration required.",
        )
    hospital_id = staff_res.data[0]["hospital_id"]

    # 2. Fetch report by report_id or id
    clean_rep_id = report_id.strip()
    q = client.table("medical_reports").select("id, report_id, patient_id, hospital_id, file_storage_path, title")
    if clean_rep_id.startswith("REP-"):
        rep_res = q.eq("report_id", clean_rep_id).execute()
    else:
        rep_res = q.eq("id", clean_rep_id).execute()

    if not rep_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical report not found.",
        )
    report = rep_res.data[0]

    # 3. Check authorization: hospital issued report OR active grant exists
    is_authorized = str(report.get("hospital_id")) == str(hospital_id)
    if not is_authorized:
        grant_res = client.table("record_access_grants").select("id, scope, report_ids").eq("patient_id", report["patient_id"]).eq("recipient_hospital_id", hospital_id).eq("is_revoked", False).gt("expires_at", datetime.now(timezone.utc).isoformat()).execute()
        if grant_res.data:
            grant = grant_res.data[0]
            if grant.get("scope") == "all" or (report["id"] in (grant.get("report_ids") or [])):
                is_authorized = True

    if not is_authorized:
        client_ip = request.client.host if request.client else "127.0.0.1"
        audit_service.log_security_event(
            client=client,
            action="medical_report_access_denied",
            entity_type="medical_report",
            entity_id=report["report_id"],
            ip_address=client_ip,
            actor_user_id=current_user.id,
            details={"reason": "hospital_not_authorized_for_report", "report_id": report["report_id"]},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your hospital is not authorized to download this report.",
        )

    # 4. Generate signed URL
    storage_path = report.get("file_storage_path")
    try:
        signed_res = client.storage.from_(settings.STORAGE_BUCKET_NAME).create_signed_url(storage_path, 300)
        signed_url = signed_res.get("signedURL") or signed_res.get("signedUrl")
        if not signed_url:
            raise Exception("Signed URL not returned")
    except Exception as e:
        logger.error("Failed to generate download URL for %s: %s", storage_path, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate secure report download URL.",
        )

    return {
        "report_id": report["report_id"],
        "title": report["title"],
        "download_url": signed_url,
        "expires_in_seconds": 300,
    }


@router.post(
    "/grant-access",
    response_model=GrantHospitalAccessResponse,
    summary="Patient grants records access to a hospital organization",
)
def grant_hospital_access(
    payload: GrantHospitalAccessRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Allows an authenticated patient to grant institutional record access to a hospital."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable.",
        )

    # 1. Fetch patient profile
    prof_res = client.table("patient_profiles").select("id, patient_id").eq("user_id", str(current_user.id)).execute()
    if not prof_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )
    patient = prof_res.data[0]

    # 2. Fetch hospital by registration number
    clean_reg = payload.hospital_registration_number.strip().upper()
    hosp_res = client.table("hospitals").select("id, name, is_active, verification_status").eq("registration_number", clean_reg).execute()
    if not hosp_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital organization '{clean_reg}' not found.",
        )
    hosp = hosp_res.data[0]
    if not hosp.get("is_active") or hosp.get("verification_status") != "verified":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hospital '{hosp['name']}' is not verified or currently active.",
        )

    # 3. Create or update record_access_grants
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days or 30)
    dummy_token_hash = "institutional_" + str(uuid4()).replace("-", "")

    client.table("record_access_grants").insert({
        "patient_id": patient["id"],
        "recipient_hospital_id": hosp["id"],
        "grant_token_hash": dummy_token_hash,
        "scope": "all",
        "expires_at": expires_at.isoformat(),
        "is_revoked": False,
    }).execute()

    return GrantHospitalAccessResponse(
        success=True,
        message=f"Access successfully granted to {hosp['name']}.",
        hospital_name=hosp["name"],
        expires_at=expires_at,
    )
