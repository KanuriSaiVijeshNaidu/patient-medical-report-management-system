from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.core.config import settings
from app.core.database import get_supabase_client, is_db_configured
from app.core.security import generate_patient_id, hash_phone, mask_phone
from app.core.auth import get_current_user, AuthenticatedUser
from app.core.rate_limit import rate_limiter, get_client_ip
from app.models.schemas import (
    PatientProfileCreate,
    PatientProfileUpdate,
    PatientProfileResponse,
    AccountRecoveryInitiateRequest,
    AccountRecoveryInitiateResponse,
    AccountRecoveryVerifyRequest,
    AccountRecoveryVerifyResponse,
)

router = APIRouter()


@router.get(
    "/me",
    response_model=PatientProfileResponse,
    summary="Get authenticated patient profile",
)
def get_my_patient_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieves the patient profile linked to the authenticated user.

    Identity is derived strictly from the verified JWT, preventing access to other patients' records.
    """
    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured. Set SUPABASE_URL and SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed. Verify Supabase credentials in backend/.env.",
        )

    response = (
        client.table("patient_profiles")
        .select("*")
        .eq("user_id", str(current_user.id))
        .execute()
    )

    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found. Please complete profile registration.",
        )

    profile = response.data[0]
    return PatientProfileResponse(
        id=UUID(profile["id"]),
        patient_id=profile["patient_id"],
        full_name=profile["full_name"],
        date_of_birth=profile["date_of_birth"],
        gender=profile["gender"],
        blood_group=profile.get("blood_group"),
        emergency_contact_phone=profile.get("emergency_contact_phone"),
        verification_status=profile["verification_status"],
        phone_masked=mask_phone(current_user.phone) if current_user.phone else None,
        created_at=profile["created_at"],
        updated_at=profile.get("updated_at"),
        masked_aadhaar_ref=profile.get("masked_aadhaar_ref"),
    )


@router.post(
    "/profile",
    response_model=PatientProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or retrieve patient profile after OTP authentication",
)
def create_patient_profile(
    payload: PatientProfileCreate,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Creates a new patient profile after phone authentication, or idempotently returns

    the existing profile. Enforces duplicate prevention and generates a permanent Patient ID.
    Rate-limited to prevent abuse.
    """
    client_ip = get_client_ip(request)
    rate_limiter.check("profile_registration", client_ip, max_requests=10, window_seconds=900)

    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured. Set SUPABASE_URL and SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed. Verify Supabase credentials in backend/.env.",
        )

    # 1. Idempotency check: Does profile already exist for this user?
    existing_profile = (
        client.table("patient_profiles")
        .select("*")
        .eq("user_id", str(current_user.id))
        .execute()
    )

    if existing_profile.data and len(existing_profile.data) > 0:
        # Profile already registered for this authenticated user -> return without creating duplicate
        profile = existing_profile.data[0]
        return PatientProfileResponse(
            id=UUID(profile["id"]),
            patient_id=profile["patient_id"],
            full_name=profile["full_name"],
            date_of_birth=profile["date_of_birth"],
            gender=profile["gender"],
            blood_group=profile.get("blood_group"),
            emergency_contact_phone=profile.get("emergency_contact_phone"),
            verification_status=profile["verification_status"],
            phone_masked=mask_phone(current_user.phone) if current_user.phone else None,
            created_at=profile["created_at"],
            updated_at=profile.get("updated_at"),
            masked_aadhaar_ref=profile.get("masked_aadhaar_ref"),
        )

    # 2. De-duplication check: Is this phone already linked to another user account?
    user_phone = current_user.phone or ""
    phone_checksum = hash_phone(user_phone) if user_phone else ""

    if phone_checksum:
        duplicate_check = (
            client.table("patient_profiles")
            .select("id, patient_id")
            .eq("phone_hash", phone_checksum)
            .execute()
        )
        if duplicate_check.data and len(duplicate_check.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A medical profile is already associated with this verified phone number. Please log in or initiate account recovery if your number has changed.",
            )

    # 3. Ensure user row exists in public.users table
    user_record = (
        client.table("users").select("id").eq("id", str(current_user.id)).execute()
    )
    if not user_record.data or len(user_record.data) == 0:
        client.table("users").insert({
            "id": str(current_user.id),
            "phone_e164": user_phone,
            "role": "patient",
            "is_active": True,
        }).execute()

    # 4. Generate unique, permanent Patient ID with collision retry
    new_patient_id = ""
    for _ in range(5):
        candidate_id = generate_patient_id()
        collision_check = (
            client.table("patient_profiles")
            .select("id")
            .eq("patient_id", candidate_id)
            .execute()
        )
        if not collision_check.data:
            new_patient_id = candidate_id
            break

    if not new_patient_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique Patient ID. Please retry.",
        )

    # 5. Insert new patient profile
    profile_data = {
        "patient_id": new_patient_id,
        "user_id": str(current_user.id),
        "full_name": payload.full_name.strip(),
        "date_of_birth": str(payload.date_of_birth),
        "gender": payload.gender,
        "blood_group": payload.blood_group,
        "emergency_contact_phone": payload.emergency_contact_phone,
        "phone_hash": phone_checksum,
        "verification_status": "phone_verified" if user_phone else "unverified",
    }

    insert_result = client.table("patient_profiles").insert(profile_data).execute()
    if not insert_result.data or len(insert_result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save patient profile.",
        )

    new_profile = insert_result.data[0]

    # 6. Audit log entry
    client.table("audit_logs").insert({
        "actor_user_id": str(current_user.id),
        "actor_role": "patient",
        "action": "patient_profile_created",
        "entity_type": "patient_profile",
        "entity_id": new_profile["id"],
        "ip_address": client_ip,
        "details": {"patient_id": new_patient_id},
    }).execute()

    return PatientProfileResponse(
        id=UUID(new_profile["id"]),
        patient_id=new_profile["patient_id"],
        full_name=new_profile["full_name"],
        date_of_birth=new_profile["date_of_birth"],
        gender=new_profile["gender"],
        blood_group=new_profile.get("blood_group"),
        emergency_contact_phone=new_profile.get("emergency_contact_phone"),
        verification_status=new_profile["verification_status"],
        phone_masked=mask_phone(user_phone) if user_phone else None,
        created_at=new_profile["created_at"],
        updated_at=new_profile.get("updated_at"),
    )


@router.patch(
    "/me",
    response_model=PatientProfileResponse,
    summary="Update authenticated patient contact and clinical details",
)
def update_my_patient_profile(
    payload: PatientProfileUpdate,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Updates non-identity patient details (blood group, emergency contact).

    Identity fields (patient_id, user_id, verification_status) are strictly immutable.
    """
    client_ip = get_client_ip(request)
    rate_limiter.check("profile_update", client_ip, max_requests=20, window_seconds=900)

    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured. Set SUPABASE_URL and SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed.",
        )

    # Check profile exists
    existing = (
        client.table("patient_profiles")
        .select("*")
        .eq("user_id", str(current_user.id))
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    updates = {}
    if payload.blood_group is not None:
        updates["blood_group"] = payload.blood_group
    if payload.emergency_contact_phone is not None:
        updates["emergency_contact_phone"] = payload.emergency_contact_phone
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    updated = (
        client.table("patient_profiles")
        .update(updates)
        .eq("user_id", str(current_user.id))
        .execute()
    )

    profile = updated.data[0]

    # Audit log entry
    client.table("audit_logs").insert({
        "actor_user_id": str(current_user.id),
        "actor_role": "patient",
        "action": "patient_profile_updated",
        "entity_type": "patient_profile",
        "entity_id": profile["id"],
        "ip_address": client_ip,
        "details": {"updated_fields": list(updates.keys())},
    }).execute()

    return PatientProfileResponse(
        id=UUID(profile["id"]),
        patient_id=profile["patient_id"],
        full_name=profile["full_name"],
        date_of_birth=profile["date_of_birth"],
        gender=profile["gender"],
        blood_group=profile.get("blood_group"),
        emergency_contact_phone=profile.get("emergency_contact_phone"),
        verification_status=profile["verification_status"],
        phone_masked=mask_phone(current_user.phone) if current_user.phone else None,
        created_at=profile["created_at"],
        updated_at=profile.get("updated_at"),
    )


@router.post(
    "/recovery/initiate",
    response_model=AccountRecoveryInitiateResponse,
    summary="Initiate account recovery for phone number change",
)
def initiate_account_recovery(
    payload: AccountRecoveryInitiateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Initiates an account recovery request when a patient loses their phone number.

    Security Audit Controls:
    1. Server-side sliding window rate limiting prevents brute-forcing Patient IDs and dates of birth.
    2. Demographic knowledge alone (DOB) is strictly insufficient to authorize an account transfer.
    3. The request is created in 'pending_institutional_approval' status.
    4. Since automated secondary KYC/email channels are unconfigured in this phase, it fails safely,
       directing the patient to in-person hospital desk verification with government photo ID.
    """
    client_ip = get_client_ip(request)
    # Rate limit: max 5 recovery attempts per 15 minutes per IP
    rate_limiter.check("recovery_initiate", client_ip, max_requests=5, window_seconds=900)

    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured. Set SUPABASE_URL and SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed.",
        )

    # 1. Lookup target patient profile
    target_profile = (
        client.table("patient_profiles")
        .select("*")
        .eq("patient_id", payload.target_patient_id.strip())
        .execute()
    )

    # Unified error to prevent user enumeration / timing attacks
    invalid_challenge_err = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid recovery request. Verification challenge details do not match or account recovery is restricted.",
    )

    if not target_profile.data:
        raise invalid_challenge_err

    target = target_profile.data[0]

    # Prevent recovering an account already owned by caller
    if str(target["user_id"]) == str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your current session already owns this Patient ID.",
        )

    # 2. Verify identity challenge: DOB must match strictly
    if str(target["date_of_birth"]) != str(payload.challenge_date_of_birth):
        raise invalid_challenge_err

    # If emergency contact is recorded, check secondary challenge
    if target.get("emergency_contact_phone") and payload.challenge_emergency_contact_phone:
        if target["emergency_contact_phone"].strip() != payload.challenge_emergency_contact_phone.strip():
            raise invalid_challenge_err

    # 3. Create recovery request in pending_institutional_approval state
    recovery_id = uuid4()
    client.table("patient_recovery_requests").insert({
        "id": str(recovery_id),
        "patient_profile_id": target["id"],
        "old_phone_hash": target["phone_hash"],
        "new_phone_e164": current_user.phone or "pending",
        "recovery_channel": "hospital_desk_required",
        "status": "pending_institutional_approval",
        "expires_at": (datetime.now(timezone.utc)).isoformat(),
    }).execute()

    # Log recovery initiation attempt in audit trail
    client.table("audit_logs").insert({
        "actor_user_id": str(current_user.id),
        "actor_role": "patient",
        "action": "patient_recovery_initiated",
        "entity_type": "patient_recovery_request",
        "entity_id": str(recovery_id),
        "ip_address": client_ip,
        "details": {"target_patient_id": target["patient_id"]},
    }).execute()

    # Fail safely: Demographic data alone cannot authorize phone transfer.
    return AccountRecoveryInitiateResponse(
        recovery_request_id=recovery_id,
        target_patient_id=target["patient_id"],
        status="pending_institutional_approval",
        message=(
            "Demographic pre-check confirmed. To prevent unauthorized account takeover, "
            "phone number re-linking requires in-person hospital desk verification with government photo ID. "
            "Automated transfer via demographic data alone is disabled."
        ),
    )


@router.post(
    "/recovery/verify",
    response_model=AccountRecoveryVerifyResponse,
    summary="Complete account recovery and re-link profile to new authenticated phone",
)
def verify_account_recovery(
    payload: AccountRecoveryVerifyRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Completes account recovery only when an authorized secondary verification channel

    (e.g., in-person hospital staff approval or verified KYC) has validated the transfer.
    Demographic knowledge alone is rejected.
    """
    client_ip = get_client_ip(request)
    rate_limiter.check("recovery_verify", client_ip, max_requests=5, window_seconds=900)

    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unconfigured. Set SUPABASE_URL and SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed.",
        )

    # 1. Fetch recovery request
    recovery_req = (
        client.table("patient_recovery_requests")
        .select("*")
        .eq("id", str(payload.recovery_request_id))
        .execute()
    )

    if not recovery_req.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired recovery request.",
        )

    req = recovery_req.data[0]

    # Security check: Must be formally approved by institutional staff or verified KYC
    if req["status"] != "approved_by_staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Account recovery cannot be completed. Demographic knowledge alone is insufficient to authorize "
                "phone number transfer. An in-person hospital desk verification or approved administrative authorization "
                "is required to approve this request before profile transfer."
            ),
        )

    patient_profile_id = req["patient_profile_id"]

    # 2. Update patient profile user_id to current_user.id and update phone_hash
    new_phone_hash = hash_phone(current_user.phone) if current_user.phone else ""
    client.table("patient_profiles").update({
        "user_id": str(current_user.id),
        "phone_hash": new_phone_hash,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", patient_profile_id).execute()

    # 3. Mark recovery request as completed
    client.table("patient_recovery_requests").update({
        "status": "completed",
    }).eq("id", str(payload.recovery_request_id)).execute()

    # 4. Audit log entry
    client.table("audit_logs").insert({
        "actor_user_id": str(current_user.id),
        "actor_role": "patient",
        "action": "patient_account_recovered",
        "entity_type": "patient_profile",
        "entity_id": patient_profile_id,
        "ip_address": client_ip,
        "details": {"recovery_request_id": str(payload.recovery_request_id)},
    }).execute()

    # Fetch patient_id for confirmation
    p = client.table("patient_profiles").select("patient_id").eq("id", patient_profile_id).execute()
    patient_id = p.data[0]["patient_id"] if p.data else ""

    return AccountRecoveryVerifyResponse(
        success=True,
        patient_id=patient_id,
        message="Account successfully recovered. All medical records remain linked to your Patient ID.",
    )
