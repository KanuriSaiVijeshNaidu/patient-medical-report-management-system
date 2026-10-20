import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core.audit import audit_service
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.core.database import get_supabase_client, is_db_configured
from app.core.rate_limit import rate_limiter, get_client_ip
from app.core.middleware import get_request_id
from app.models.schemas import (
    CreateReportShareRequest,
    RevokeShareResponse,
    ShareGrantResponse,
    SharedReportItem,
    SharedReportViewResponse,
)

logger = logging.getLogger("api.access")

router = APIRouter()


def _get_caller_patient_profile(client, user_id: UUID) -> dict:
    """Retrieves authoritative patient profile belonging to the verified caller."""
    res = (
        client.table("patient_profiles")
        .select("id, patient_id")
        .eq("user_id", str(user_id))
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found. Please complete profile registration.",
        )
    return res.data[0]


def _resolve_report_uuid(client, report_identifier: str, patient_profile_id: str) -> UUID:
    """Resolves report UUID asserting it belongs to caller's patient profile."""
    try:
        report_uuid = UUID(report_identifier)
        lookup = (
            client.table("medical_reports")
            .select("id")
            .eq("id", str(report_uuid))
            .eq("patient_id", patient_profile_id)
            .execute()
        )
        if lookup.data:
            return report_uuid
    except ValueError:
        lookup = (
            client.table("medical_reports")
            .select("id")
            .eq("report_id", report_identifier)
            .eq("patient_id", patient_profile_id)
            .execute()
        )
        if lookup.data:
            return UUID(lookup.data[0]["id"])

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Medical report not found or access denied.",
    )


@router.post(
    "/create-share",
    response_model=ShareGrantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a time-bound, revocable QR share grant for one or more reports",
)
def create_report_share(
    payload: CreateReportShareRequest,
    request: Request,
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Generates an expiring share grant for one or more specific reports owned by the patient.

    Security guarantees:
    - Authoritative owner check: all reports must belong strictly to the authenticated user.
    - High-entropy, cryptographically random raw token generated server-side.
    - Only the SHA-256 hash is persisted in the database; raw token is never stored.
    - Atomic RPC ensures grant creation and durable audit logging happen together.
    - Raw token is never written to audit logs or system logs.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)
    rate_limiter.check("create_share", client_ip, max_requests=30, window_seconds=3600)

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
    patient_profile_id = str(profile["id"])

    # 2. Extract and validate requested report identifiers
    raw_report_ids: List[str] = []
    if payload.report_ids:
        for rid in payload.report_ids:
            if rid and str(rid).strip() and str(rid).strip() not in raw_report_ids:
                raw_report_ids.append(str(rid).strip())
    if payload.report_id and str(payload.report_id).strip():
        rid = str(payload.report_id).strip()
        if rid not in raw_report_ids:
            raw_report_ids.insert(0, rid)

    if not raw_report_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one medical report must be selected for sharing.",
        )

    # 3. Verify ownership and resolve target report UUIDs
    resolved_uuids: List[UUID] = []
    for rid in raw_report_ids:
        try:
            report_uuid = _resolve_report_uuid(client, rid, patient_profile_id)
            if report_uuid not in resolved_uuids:
                resolved_uuids.append(report_uuid)
        except HTTPException as e:
            audit_service.log_security_event(
                client=client,
                action="report_share_access_denied",
                entity_type="medical_report",
                entity_id=rid,
                ip_address=client_ip,
                actor_user_id=current_user.id,
                details={"reason": "unauthorized_share_attempt_wrong_owner", "request_id": req_id},
                request_id=req_id,
            )
            raise e

    # 4. Validate expiration duration
    expiry_sec = payload.expires_in_seconds or settings.DEFAULT_SHARE_EXPIRATION_SECONDS
    if expiry_sec < 60 or expiry_sec > 86400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Share duration must be between 60 seconds and 86400 seconds (24 hours).",
        )

    # 5. Generate high-entropy cryptographic token and compute SHA-256 hash
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # 6. Call atomic RPC (supports multi-report grant creation or single-report fallback)
    if len(resolved_uuids) == 1:
        rpc_params = {
            "p_auth_user_id": str(current_user.id),
            "p_report_id": str(resolved_uuids[0]),
            "p_token_hash": token_hash,
            "p_expires_in_seconds": expiry_sec,
            "p_ip_address": client_ip,
            "p_request_id": req_id,
        }
        rpc_name = "create_report_access_grant_atomic"
    else:
        rpc_params = {
            "p_auth_user_id": str(current_user.id),
            "p_report_ids": [str(u) for u in resolved_uuids],
            "p_token_hash": token_hash,
            "p_expires_in_seconds": expiry_sec,
            "p_ip_address": client_ip,
            "p_request_id": req_id,
        }
        rpc_name = "create_multi_report_access_grant_atomic"

    try:
        res = client.rpc(rpc_name, rpc_params).execute()
        grant_data = res.data
    except Exception as e:
        err_msg = str(e)
        logger.error("Failed to execute %s: %s", rpc_name, err_msg)
        if "insufficient_privilege" in err_msg or "access denied" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied or report not owned by authenticated user.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create share grant: {err_msg}",
        )

    share_url = f"{settings.FRONTEND_BASE_URL}/share/{raw_token}"
    report_codes = grant_data.get("report_ids") or [str(grant_data.get("report_id", ""))]

    return ShareGrantResponse(
        grant_id=UUID(grant_data["grant_id"]),
        report_id=str(grant_data.get("report_id", "")),
        report_ids=report_codes,
        reports_count=grant_data.get("reports_count", len(resolved_uuids)),
        share_url=share_url,
        raw_token=raw_token,
        expires_at=datetime.fromisoformat(str(grant_data["expires_at"]).replace("Z", "+00:00")),
        expires_in_seconds=grant_data["expires_in_seconds"],
    )


@router.delete(
    "/revoke/{grant_id}",
    response_model=RevokeShareResponse,
    status_code=status.HTTP_200_OK,
    summary="Immediately revoke an active share grant",
)
def revoke_report_share(
    grant_id: UUID,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Immediately revokes an active share grant, terminating external access.

    Enforces:
    - Caller must own the patient profile that created the grant.
    - Emits durable audit log in the same transaction.
    """
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

    rpc_params = {
        "p_auth_user_id": str(current_user.id),
        "p_grant_id": str(grant_id),
        "p_ip_address": client_ip,
        "p_request_id": req_id,
    }

    try:
        res = client.rpc("revoke_report_access_grant_atomic", rpc_params).execute()
        data = res.data
    except Exception as e:
        err_msg = str(e)
        logger.error("Failed to execute revoke_report_access_grant_atomic: %s", err_msg)
        if "no_data_found" in err_msg or "not found" in err_msg or "insufficient_privilege" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Share grant not found or access denied.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not revoke share grant: {err_msg}",
        )

    return RevokeShareResponse(
        success=True,
        message="Medical report share revoked successfully.",
        grant_id=UUID(data["grant_id"]),
        revoked_at=datetime.fromisoformat(str(data["revoked_at"]).replace("Z", "+00:00")),
    )


@router.get(
    "/view/{token}",
    response_model=SharedReportViewResponse,
    summary="Public recipient endpoint for validated zero-install report access",
)
def view_shared_report(
    token: str,
    request: Request,
    response: Response,
):
    """Validates an incoming bearer share token and provides temporary report access.

    Security guarantees:
    - Rate-limits token lookup attempts per client IP to prevent brute-force guessing.
    - Validates token hash, expiration, and revocation status atomically.
    - If token is invalid, expired, or revoked, returns a generic 404 without leaking state.
    - Emits durable audit log for both valid access and unauthorized attempts.
    - Generates a short-lived pre-signed download URL only after authorization.
    - Does NOT disclose patient identity, patient IDs, or unrelated medical data.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)

    # 1. Rate limiting against token brute-force / abuse
    try:
        rate_limiter.check("share_access", client_ip, max_requests=30, window_seconds=60)
    except HTTPException as e:
        client = get_supabase_client()
        if client:
            audit_service.log_security_event(
                client=client,
                action="security_rate_limit_exceeded",
                entity_type="record_access_grant",
                entity_id="anonymous",
                ip_address=client_ip,
                details={"endpoint": "/api/v1/access/view", "request_id": req_id},
                request_id=req_id,
            )
        raise e

    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is currently unavailable.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed.",
        )

    # 2. Derive token hash
    if not token or len(token) < 16:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared medical report not found, expired, or access has been revoked.",
        )

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # 3. Call atomic validation RPC
    rpc_params = {
        "p_token_hash": token_hash,
        "p_ip_address": client_ip,
        "p_request_id": req_id,
    }

    try:
        res = client.rpc("validate_and_access_shared_report_atomic", rpc_params).execute()
        grant_data = res.data
        if not grant_data:
            raise Exception("no_data_found")
    except Exception as e:
        err_msg = str(e)
        logger.warning("Share access validation rejected: %s", err_msg)

        # Audit rejected attempt without leaking raw token
        audit_service.log_security_event(
            client=client,
            action="report_share_access_denied",
            entity_type="record_access_grant",
            entity_id="unknown",
            ip_address=client_ip,
            details={"reason": "invalid_expired_or_revoked_token", "request_id": req_id},
            request_id=req_id,
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared medical report not found, expired, or access has been revoked.",
        )

    # 4. Generate short-lived signed download URLs for all authorized reports
    raw_reports = grant_data.get("reports")
    if not raw_reports or not isinstance(raw_reports, list):
        raw_reports = [grant_data]

    expiry = settings.SIGNED_URL_EXPIRATION_SECONDS
    report_items: List[SharedReportItem] = []

    for rep in raw_reports:
        storage_path = rep.get("file_storage_path")
        if not storage_path:
            logger.warning("Report %s is missing file_storage_path", rep.get("report_id"))
            continue

        try:
            signed_res = client.storage.from_(settings.STORAGE_BUCKET_NAME).create_signed_url(
                storage_path,
                expiry,
            )
            signed_url = signed_res.get("signedURL") or signed_res.get("signedUrl")
            if not signed_url:
                raise Exception("No signed URL in storage response")
        except Exception as e:
            logger.error("Failed to create signed URL for shared report %s: %s", rep.get("report_id"), str(e))
            signed_url = ""

        report_items.append(
            SharedReportItem(
                report_id=rep["report_id"],
                title=rep["title"],
                category=str(rep["category"]),
                report_date=rep["report_date"],
                file_size_bytes=int(rep["file_size_bytes"]),
                mime_type=rep["mime_type"],
                verification_status=rep["verification_status"],
                download_url=signed_url,
                download_url_expires_in_seconds=expiry,
            )
        )

    if not report_items:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report storage file references unavailable.",
        )

    primary = report_items[0]

    return SharedReportViewResponse(
        grant_id=UUID(grant_data["grant_id"]),
        report_id=primary.report_id,
        title=primary.title,
        category=primary.category,
        report_date=primary.report_date,
        file_size_bytes=primary.file_size_bytes,
        mime_type=primary.mime_type,
        verification_status=primary.verification_status,
        download_url=primary.download_url,
        download_url_expires_in_seconds=expiry,
        share_expires_at=datetime.fromisoformat(str(grant_data["share_expires_at"]).replace("Z", "+00:00")),
        reports=report_items,
    )
