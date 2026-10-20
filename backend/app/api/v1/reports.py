import hashlib
import logging
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from app.core.config import settings
from app.core.database import get_supabase_client, is_db_configured
from app.core.security import generate_report_id
from app.core.auth import get_current_user, AuthenticatedUser
from app.core.rate_limit import rate_limiter, get_client_ip
from app.core.middleware import get_request_id
from app.core.audit import audit_service
from app.models.schemas import (
    MedicalReportResponse,
    ReportCategory,
    ReportDownloadUrlResponse,
    ReportDeleteResponse,
)

logger = logging.getLogger("security.reports")
router = APIRouter()

ALLOWED_CATEGORIES = {
    "blood_test",
    "xray",
    "ct_scan",
    "mri",
    "prescription",
    "discharge_summary",
    "other",
}
PDF_MAGIC_BYTES = b"%PDF-"
CHUNK_SIZE = 64 * 1024  # 64 KB streaming chunks


def _get_caller_patient_profile(client, user_id: UUID) -> dict:
    """Fetches the patient profile strictly owned by the authenticated caller."""
    res = client.table("patient_profiles").select("id, patient_id").eq("user_id", str(user_id)).execute()
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found. Please register your profile first.",
        )
    return res.data[0]


@router.post(
    "/upload",
    response_model=MedicalReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new medical report PDF document",
)
async def upload_medical_report(
    request: Request,
    file: UploadFile = File(..., description="PDF document of the medical report"),
    title: str = Form(..., description="Title of the medical report (3-255 characters)"),
    category: str = Form(..., description="Report category allowlist"),
    report_date: date = Form(..., description="Date on which the test or consultation occurred"),
    description: Optional[str] = Form(None, description="Optional medical description / clinical notes"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Securely uploads an authenticated patient's medical report.

    Validates:
    - User identity derived strictly from verified JWT.
    - PDF extension, MIME type, and '%PDF-' magic byte signature.
    - Enforces configured maximum file size during streaming.
    - Server-generated unpredictable storage paths.
    - Atomic database record creation and audit log emission.
    - Automatic orphan cleanup if storage or database operations fail.
    """
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)
    rate_limiter.check("report_upload", client_ip, max_requests=30, window_seconds=3600)

    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed.",
        )

    # 1. Authoritative caller profile resolution
    profile = _get_caller_patient_profile(client, current_user.id)
    patient_profile_id = profile["id"]

    # 2. Metadata validations
    clean_title = title.strip()
    if len(clean_title) < 3 or len(clean_title) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report title must be between 3 and 255 characters.",
        )

    clean_category = category.strip().lower()
    if clean_category not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category '{category}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}.",
        )

    if report_date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report date cannot be in the future.",
        )

    clean_description = description.strip() if description else None
    if clean_description and len(clean_description) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Description cannot exceed 1000 characters.",
        )

    # 3. File extension & MIME type validation
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents are accepted for medical reports (.pdf extension required).",
        )

    if file.content_type and file.content_type.lower() != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid MIME type '{file.content_type}'. Must be 'application/pdf'.",
        )

    # 4. Streaming read, file size enforcement, magic byte validation & SHA-256 computation
    file_bytes_list = []
    total_size = 0
    max_size = settings.MAX_REPORT_FILE_SIZE_BYTES
    sha256_hasher = hashlib.sha256()
    is_first_chunk = True

    try:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > max_size:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum allowed size of {max_size // (1024 * 1024)} MB.",
                )

            if is_first_chunk:
                is_first_chunk = False
                if not chunk.startswith(PDF_MAGIC_BYTES):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid file signature. File does not contain a valid PDF magic header (%PDF-).",
                    )

            sha256_hasher.update(chunk)
            file_bytes_list.append(chunk)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error reading uploaded file: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file payload.",
        )
    finally:
        await file.close()

    if total_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    file_bytes = b"".join(file_bytes_list)
    file_checksum = sha256_hasher.hexdigest()

    # 5. Generate server-side storage path and candidate Report ID
    file_uuid = str(uuid4())
    storage_path = f"reports/{patient_profile_id}/{file_uuid}.pdf"
    candidate_report_id = generate_report_id()

    # 6. Upload file to private Supabase Storage
    try:
        client.storage.from_(settings.STORAGE_BUCKET_NAME).upload(
            storage_path,
            file_bytes,
            {"content-type": "application/pdf"},
        )
    except Exception as e:
        logger.error("Failed to upload file to storage: %s", str(e))
        audit_service.log_security_event(
            client=client,
            action="medical_report_upload_failed",
            entity_type="medical_report",
            entity_id=candidate_report_id,
            ip_address=client_ip,
            actor_user_id=current_user.id,
            details={"reason": "storage_upload_error", "request_id": req_id},
            request_id=req_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store report file. Please try again later.",
        )

    # 7. Atomic Database Insertion and Audit Log Generation
    metadata_payload = {}
    if clean_description:
        metadata_payload["description"] = clean_description
    metadata_payload["original_filename"] = filename

    rpc_params = {
        "p_auth_user_id": str(current_user.id),
        "p_report_id": candidate_report_id,
        "p_title": clean_title,
        "p_category": clean_category,
        "p_report_date": str(report_date),
        "p_file_storage_path": storage_path,
        "p_file_checksum_sha256": file_checksum,
        "p_file_size_bytes": total_size,
        "p_mime_type": "application/pdf",
        "p_metadata": metadata_payload,
        "p_ip_address": client_ip,
        "p_request_id": req_id,
    }

    try:
        res = client.rpc("create_medical_report_atomic", rpc_params).execute()
        created_report = res.data
    except Exception as e:
        # Prevent orphaned storage file: Roll back storage file upload!
        logger.warning("Database record creation failed, cleaning up orphaned storage file: %s", storage_path)
        try:
            client.storage.from_(settings.STORAGE_BUCKET_NAME).remove([storage_path])
        except Exception as cleanup_err:
            logger.error("Failed to delete orphaned storage file %s: %s", storage_path, str(cleanup_err))

        audit_service.log_security_event(
            client=client,
            action="medical_report_upload_failed",
            entity_type="medical_report",
            entity_id=candidate_report_id,
            ip_address=client_ip,
            actor_user_id=current_user.id,
            details={"reason": "database_error", "error": str(e), "request_id": req_id},
            request_id=req_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save medical report metadata: {str(e)}",
        )

    return MedicalReportResponse(
        id=UUID(created_report["id"]),
        report_id=created_report["report_id"],
        patient_id=UUID(created_report["patient_id"]),
        upload_source="patient",
        title=created_report["title"],
        category=created_report["category"],
        report_date=date.fromisoformat(str(created_report["report_date"])),
        file_size_bytes=created_report["file_size_bytes"],
        mime_type=created_report["mime_type"],
        verification_status=created_report["verification_status"],
        created_at=datetime.fromisoformat(str(created_report["created_at"]).replace("Z", "+00:00")),
        metadata=created_report.get("metadata", {}),
    )


@router.get(
    "",
    response_model=List[MedicalReportResponse],
    summary="List medical reports for the current authenticated patient",
)
def list_my_medical_reports(
    request: Request,
    category: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Lists categorized reports strictly belonging to the authenticated patient."""
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)

    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed.",
        )

    profile = _get_caller_patient_profile(client, current_user.id)
    patient_profile_id = profile["id"]

    query = (
        client.table("medical_reports")
        .select("*")
        .eq("patient_id", str(patient_profile_id))
    )

    if category:
        clean_cat = category.strip().lower()
        if clean_cat in ALLOWED_CATEGORIES:
            query = query.eq("category", clean_cat)

    query = query.order("report_date", desc=True).order("created_at", desc=True)
    res = query.execute()

    reports = []
    for r in (res.data or []):
        reports.append(
            MedicalReportResponse(
                id=UUID(r["id"]),
                report_id=r["report_id"],
                patient_id=UUID(r["patient_id"]),
                hospital_id=UUID(r["hospital_id"]) if r.get("hospital_id") else None,
                upload_source=r["upload_source"],
                title=r["title"],
                category=r["category"],
                report_date=date.fromisoformat(str(r["report_date"])),
                file_size_bytes=r["file_size_bytes"],
                mime_type=r["mime_type"],
                verification_status=r["verification_status"],
                created_at=datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")),
                metadata=r.get("metadata", {}),
            )
        )

    return reports


@router.get(
    "/patient/{patient_id}",
    response_model=List[MedicalReportResponse],
    summary="List patient medical reports with security authorization",
)
def list_patient_reports(
    patient_id: UUID,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Lists categorized reports for an authorized patient (enforcing strict ownership)."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured.",
        )

    profile = _get_caller_patient_profile(client, current_user.id)
    if str(profile["id"]) != str(patient_id):
        # Cross-patient request: Never leak records or confirm identity
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient reports not found or access denied.",
        )

    return list_my_medical_reports(request=request, current_user=current_user)


@router.get(
    "/{report_id}",
    response_model=MedicalReportResponse,
    summary="Get metadata for a specific medical report",
)
def get_medical_report_details(
    report_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieves report metadata with strict ownership verification."""
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured.",
        )

    profile = _get_caller_patient_profile(client, current_user.id)

    # Query by UUID id or formatted report_id
    query = client.table("medical_reports").select("*")
    try:
        uuid_val = UUID(report_id)
        query = query.or_(f"id.eq.{str(uuid_val)},report_id.eq.{report_id}")
    except ValueError:
        query = query.eq("report_id", report_id)

    res = query.execute()
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical report not found.",
        )

    r = res.data[0]

    # Enforce caller owns this report
    if str(r["patient_id"]) != str(profile["id"]):
        audit_service.log_security_event(
            client=client,
            action="medical_report_access_denied",
            entity_type="medical_report",
            entity_id=report_id,
            ip_address=client_ip,
            actor_user_id=current_user.id,
            details={"reason": "cross_patient_unauthorized_read", "request_id": req_id},
            request_id=req_id,
        )
        # Avoid leaking whether another patient's report exists
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical report not found.",
        )

    audit_service.log_security_event(
        client=client,
        action="medical_report_read",
        entity_type="medical_report",
        entity_id=str(r["id"]),
        ip_address=client_ip,
        actor_user_id=current_user.id,
        details={"report_id": r["report_id"], "category": r["category"], "request_id": req_id},
        request_id=req_id,
    )

    return MedicalReportResponse(
        id=UUID(r["id"]),
        report_id=r["report_id"],
        patient_id=UUID(r["patient_id"]),
        hospital_id=UUID(r["hospital_id"]) if r.get("hospital_id") else None,
        upload_source=r["upload_source"],
        title=r["title"],
        category=r["category"],
        report_date=date.fromisoformat(str(r["report_date"])),
        file_size_bytes=r["file_size_bytes"],
        mime_type=r["mime_type"],
        verification_status=r["verification_status"],
        created_at=datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")),
        metadata=r.get("metadata", {}),
    )


@router.post(
    "/{report_id}/download-url",
    response_model=ReportDownloadUrlResponse,
    summary="Generate a short-lived, pre-signed download URL for report viewing",
)
@router.get(
    "/{report_id}/download",
    response_model=ReportDownloadUrlResponse,
    summary="Generate a short-lived, pre-signed download URL for report viewing",
)
def get_report_download_url(
    report_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Issues a short-lived pre-signed download URL for authorized viewing.

    Enforces:
    - Caller must own the report.
    - Never accepts a raw storage path from the frontend.
    - Short expiration (default 300s).
    - Signed URL is kept out of persistent storage, audit logs, and application logs.
    """
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured.",
        )

    profile = _get_caller_patient_profile(client, current_user.id)

    query = client.table("medical_reports").select("*")
    try:
        uuid_val = UUID(report_id)
        query = query.or_(f"id.eq.{str(uuid_val)},report_id.eq.{report_id}")
    except ValueError:
        query = query.eq("report_id", report_id)

    res = query.execute()
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical report not found.",
        )

    r = res.data[0]

    # Enforce ownership
    if str(r["patient_id"]) != str(profile["id"]):
        audit_service.log_security_event(
            client=client,
            action="medical_report_access_denied",
            entity_type="medical_report",
            entity_id=report_id,
            ip_address=client_ip,
            actor_user_id=current_user.id,
            details={"reason": "cross_patient_unauthorized_download_attempt", "request_id": req_id},
            request_id=req_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical report not found.",
        )

    expiry = settings.SIGNED_URL_EXPIRATION_SECONDS
    try:
        signed_res = client.storage.from_(settings.STORAGE_BUCKET_NAME).create_signed_url(
            r["file_storage_path"],
            expiry,
        )
        signed_url = signed_res.get("signedURL") or signed_res.get("signedUrl")
        if not signed_url:
            raise Exception("No signed URL in storage response")
    except Exception as e:
        logger.error("Failed to generate signed URL for report %s: %s", report_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate secure view URL.",
        )

    # Durable audit event: records event WITHOUT logging the signed URL or token
    audit_service.log_security_event(
        client=client,
        action="medical_report_downloaded",
        entity_type="medical_report",
        entity_id=str(r["id"]),
        ip_address=client_ip,
        actor_user_id=current_user.id,
        details={
            "report_id": r["report_id"],
            "category": r["category"],
            "request_id": req_id,
            "expiry_seconds": expiry,
        },
        request_id=req_id,
    )

    return ReportDownloadUrlResponse(
        report_id=r["report_id"],
        download_url=signed_url,
        expires_in_seconds=expiry,
    )


@router.delete(
    "/{report_id}",
    response_model=ReportDeleteResponse,
    summary="Delete a medical report owned by the patient",
)
def delete_medical_report(
    report_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Deletes an authorized patient's medical report and its associated storage file."""
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured.",
        )

    profile = _get_caller_patient_profile(client, current_user.id)

    # First resolve report UUID if report_id formatted code was passed
    target_uuid = None
    try:
        target_uuid = UUID(report_id)
    except ValueError:
        lookup = client.table("medical_reports").select("id").eq("report_id", report_id).eq("patient_id", str(profile["id"])).execute()
        if lookup.data:
            target_uuid = UUID(lookup.data[0]["id"])

    if not target_uuid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical report not found or access denied.",
        )

    rpc_params = {
        "p_auth_user_id": str(current_user.id),
        "p_report_id": str(target_uuid),
        "p_ip_address": client_ip,
        "p_request_id": req_id,
    }

    try:
        res = client.rpc("delete_medical_report_atomic", rpc_params).execute()
        del_data = res.data
    except Exception as e:
        err_msg = str(e)
        if "no_data_found" in err_msg or "not found" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medical report not found or access denied.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not delete medical report: {err_msg}",
        )

    # Remove storage file
    storage_path = del_data.get("file_storage_path")
    if storage_path:
        try:
            client.storage.from_(settings.STORAGE_BUCKET_NAME).remove([storage_path])
        except Exception as e:
            logger.error("Failed to delete storage file %s after DB deletion: %s", storage_path, str(e))

    return ReportDeleteResponse(
        success=True,
        message="Medical report deleted successfully.",
        report_id=del_data.get("report_id", report_id),
    )
