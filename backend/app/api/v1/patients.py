import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.core.config import settings
from app.core.database import get_supabase_client, create_isolated_auth_client, is_db_configured
from app.core.security import (
    generate_patient_id,
    normalize_phone,
    hash_phone,
    mask_phone,
    hash_password,
    verify_password,
    create_access_token,
)
from app.core.auth import get_current_user, AuthenticatedUser
from app.core.rate_limit import rate_limiter, get_client_ip
from app.core.middleware import get_request_id
from app.core.dedup import profile_read_dedup
from app.core.audit import audit_service
from app.models.schemas import (
    PatientRegisterRequest,
    PatientRegisterResponse,
    PatientLoginRequest,
    PatientLoginResponse,
    PatientProfileCreate,
    PatientProfileUpdate,
    PatientProfileResponse,
    AccountRecoveryInitiateRequest,
    AccountRecoveryInitiateResponse,
    AccountRecoveryVerifyRequest,
    AccountRecoveryVerifyResponse,
)

logger = logging.getLogger("api.patients")
router = APIRouter()


@router.post(
    "/register",
    response_model=PatientRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new patient with username and password",
)
def register_patient(
    payload: PatientRegisterRequest,
    request: Request,
):
    """Registers a new patient with unique username, password, and demographic details.
    Enforces uniqueness of username and phone number, hashes the password using bcrypt,
    generates a permanent collision-resistant Patient ID, establishes session credentials,
    and logs the registration audit event.
    """
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)
    rate_limiter.check("patient_registration", client_ip, max_requests=10, window_seconds=900)

    clean_username = payload.username.strip().lower()
    user_phone = normalize_phone(payload.phone)
    phone_checksum = hash_phone(user_phone)
    clean_email = payload.email.strip().lower() if payload.email and payload.email.strip() else None
    client = get_supabase_client()

    # 1. Duplicate username check
    if client:
        try:
            res_cred = client.table("user_credentials").select("id").ilike("username", clean_username).execute()
            if res_cred.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username is already taken. Please choose another username.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

        try:
            res_user = client.table("users").select("id").ilike("username", clean_username).execute()
            if res_user.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username is already taken. Please choose another username.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    # 2. Duplicate phone check
    if client:
        try:
            res_phone = client.table("patient_profiles").select("id").eq("phone_hash", phone_checksum).execute()
            if res_phone.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A medical profile is already associated with this phone number. Please sign in with your username and password.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    # 2b. Duplicate email check (only when email is provided)
    if client and clean_email:
        try:
            res_email = client.table("users").select("id").ilike("email", clean_email).execute()
            if res_email.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account is already associated with this email address. Please use another email or sign in.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    # 3. Hash password using bcrypt
    password_hash = hash_password(payload.password)
    candidate_patient_id = generate_patient_id()
    user_id = None

    # 4. Create user in Supabase Auth if client is available
    if client:
        try:
            auth_attributes = {
                "password": payload.password,
                "phone": user_phone,
                "phone_confirm": True,
                "user_metadata": {
                    "username": clean_username,
                    "full_name": payload.full_name.strip(),
                    "role": "patient",
                },
            }
            if clean_email:
                auth_attributes["email"] = clean_email
                auth_attributes["email_confirm"] = True

            admin_res = client.auth.admin.create_user(auth_attributes)
            if admin_res and admin_res.user:
                user_id = UUID(admin_res.user.id)
        except Exception as auth_err:
            err_str = str(auth_err).lower()
            if "already registered" in err_str or "already exists" in err_str or "duplicate" in err_str:
                if clean_email and "email" in err_str:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="An account is already associated with this email address. Please use another email or sign in.",
                    )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username is already taken. Please choose another username.",
                )
            logger.warning("Supabase admin auth create_user fallback: %s", auth_err)

    if not user_id:
        user_id = uuid4()

    # 5. Insert into public.users
    if client:
        try:
            client.table("users").upsert({
                "id": str(user_id),
                "username": clean_username,
                "email": clean_email,
                "phone_e164": user_phone,
                "role": "patient",
                "is_active": True,
            }).execute()
        except Exception as e:
            logger.warning("Could not upsert into users table: %s", e)

    # 6. Insert into public.user_credentials
    if client:
        try:
            client.table("user_credentials").insert({
                "user_id": str(user_id),
                "username": clean_username,
                "password_hash": password_hash,
            }).execute()
        except Exception as e:
            logger.warning("Could not insert into user_credentials table: %s", e)

    # 7. Create profile in public.patient_profiles
    dob_str = payload.date_of_birth.isoformat() if payload.date_of_birth else "2000-01-01"
    profile_id = str(uuid4())
    profile_data = {
        "id": profile_id,
        "patient_id": candidate_patient_id,
        "user_id": str(user_id),
        "full_name": payload.full_name.strip(),
        "date_of_birth": dob_str,
        "gender": payload.gender,
        "blood_group": payload.blood_group,
        "phone_hash": phone_checksum,
        "verification_status": "phone_verified",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if client:
        # Try atomic RPC first
        rpc_params = {
            "p_auth_user_id": str(user_id),
            "p_full_name": payload.full_name.strip(),
            "p_date_of_birth": dob_str,
            "p_gender": payload.gender,
            "p_blood_group": payload.blood_group,
            "p_emergency_contact_phone": None,
            "p_phone_e164": user_phone,
            "p_phone_hash": phone_checksum,
            "p_patient_id": candidate_patient_id,
            "p_ip_address": client_ip,
            "p_request_id": req_id,
        }
        try:
            rpc_res = client.rpc("register_patient_profile_atomic", rpc_params).execute()
            if rpc_res.data:
                profile_data = rpc_res.data
        except Exception as rpc_err:
            logger.warning("RPC registration fallback: %s", rpc_err)
            try:
                client.table("patient_profiles").insert(profile_data).execute()
            except Exception as insert_err:
                err_msg = str(insert_err)
                if "unique" in err_msg or "already associated" in err_msg:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="A medical profile is already associated with this phone number or Patient ID.",
                    )
                if "Invalid API key" in err_msg or "PGRST301" in err_msg or "'code': 401" in err_msg:
                    logger.error("Supabase API key rejected: %s", err_msg)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Could not save patient profile: Database authentication failed (Invalid API key). Please ensure a valid Supabase service_role JWT key is configured in backend/.env.",
                    )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Could not save patient profile: {err_msg}",
                )

    # 8. Audit log
    if client:
        try:
            audit_service.log_security_event(
                client=client,
                action="patient_profile_created",
                entity_type="patient_profile",
                entity_id=str(profile_data.get("id", profile_id)),
                ip_address=client_ip,
                actor_user_id=user_id,
                user_agent=request.headers.get("user-agent"),
                details={
                    "patient_id": profile_data.get("patient_id", candidate_patient_id),
                    "username": clean_username,
                    "auth_provider": "username_password",
                    "request_id": req_id,
                },
                request_id=req_id,
            )
        except Exception as e:
            logger.warning("Could not emit audit log for registration: %s", e)

    # 9. Generate access token
    access_token = create_access_token(user_id=user_id, role="patient", username=clean_username)

    return PatientRegisterResponse(
        patient_id=profile_data.get("patient_id", candidate_patient_id),
        full_name=payload.full_name.strip(),
        username=clean_username,
        access_token=access_token,
        token_type="bearer",
        message="Registration successful. Please save your permanent Patient ID.",
    )


@router.post(
    "/login",
    response_model=PatientLoginResponse,
    summary="Authenticate patient with username and password",
)
def login_patient(
    payload: PatientLoginRequest,
    request: Request,
):
    """Authenticates patient using username and password.
    Verifies credentials via bcrypt or Supabase Auth, retrieves permanent Patient ID,
    issues a secure JWT session token, and records security audit logs.
    """
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)
    rate_limiter.check("patient_login", client_ip, max_requests=10, window_seconds=60)

    clean_username = payload.username.strip().lower()
    client = get_supabase_client()
    user_id = None
    access_token = None

    if client:
        # 1. Lookup in user_credentials table
        try:
            res_cred = client.table("user_credentials").select("user_id, password_hash").ilike("username", clean_username).execute()
            if res_cred.data:
                cred = res_cred.data[0]
                stored_hash = cred.get("password_hash")
                cand_user_id = cred.get("user_id")
                if stored_hash and verify_password(payload.password, stored_hash):
                    user_id = UUID(cand_user_id)
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid username or password.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("user_credentials query fallback: %s", e)

        # 2. Try Supabase Auth password verification if not resolved via user_credentials
        # Uses an isolated, ephemeral auth client to avoid mutating the shared service-role client
        if not user_id:
            internal_email = f"{clean_username}@patient.internal"
            try:
                auth_client = create_isolated_auth_client()
                if auth_client:
                    auth_res = auth_client.auth.sign_in_with_password({
                        "email": internal_email,
                        "password": payload.password,
                    })
                    if auth_res and auth_res.user:
                        user_id = UUID(auth_res.user.id)
                        if hasattr(auth_res, "session") and auth_res.session and getattr(auth_res.session, "access_token", None):
                            access_token = auth_res.session.access_token

                        # Sync verified credentials into user_credentials table via privileged client
                        try:
                            client.table("user_credentials").upsert({
                                "user_id": str(user_id),
                                "username": clean_username,
                                "password_hash": hash_password(payload.password),
                            }).execute()
                            client.table("users").update({"username": clean_username}).eq("id", str(user_id)).execute()
                            logger.info("Successfully synced credentials for user %s into user_credentials", clean_username)
                        except Exception as sync_e:
                            logger.warning("Credentials sync skipped for %s: %s", clean_username, sync_e)
            except Exception as auth_err:
                logger.debug("Supabase auth sign in fallback failed: %s", auth_err)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Retrieve patient profile using privileged backend client
    patient_id = None
    full_name = clean_username
    if client:
        try:
            res_prof = (
                client.table("patient_profiles")
                .select("patient_id, full_name")
                .eq("user_id", str(user_id))
                .execute()
            )
            if res_prof.data and len(res_prof.data) > 0:
                prof = res_prof.data[0]
                patient_id = prof.get("patient_id")
                full_name = prof.get("full_name", clean_username)
        except Exception as prof_err:
            err_code = getattr(prof_err, "code", None)
            err_details = getattr(prof_err, "details", None)
            err_msg = getattr(prof_err, "message", str(prof_err))
            if not err_code and hasattr(prof_err, "args") and prof_err.args and isinstance(prof_err.args[0], dict):
                err_code = prof_err.args[0].get("code")
                err_msg = prof_err.args[0].get("message", err_msg)
                err_details = prof_err.args[0].get("details")

            logger.error(
                "Database error retrieving patient profile (user_id=%s, code=%s, details=%s): %s",
                user_id,
                err_code,
                err_details,
                err_msg,
            )
            if "permission denied" in err_msg or "42501" in str(err_code) or "42501" in err_msg:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database permissions error accessing patient profile.",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error retrieving profile: {err_msg}",
            )

    if not patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found. Please complete registration.",
        )

    # 4. Generate token if not already from GoTrue session
    if not access_token:
        access_token = create_access_token(user_id=user_id, role="patient", username=clean_username)

    return PatientLoginResponse(
        access_token=access_token,
        token_type="bearer",
        patient_id=patient_id,
        username=clean_username,
        full_name=full_name,
    )



@router.get(
    "/me",
    response_model=PatientProfileResponse,
    summary="Get authenticated patient profile",
)
def get_my_patient_profile(
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieves the patient profile linked to the authenticated user.

    Identity is derived strictly from the verified JWT, preventing access to other patients' records.
    Audits access with a 15-minute sliding window deduplication policy.
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

    response = None
    try:
        response = (
            client.table("patient_profiles")
            .select("*")
            .eq("user_id", str(current_user.id))
            .execute()
        )
    except Exception as db_err:
        err_code = getattr(db_err, "code", None)
        err_details = getattr(db_err, "details", None)
        err_msg = getattr(db_err, "message", str(db_err))
        if not err_code and hasattr(db_err, "args") and db_err.args and isinstance(db_err.args[0], dict):
            err_code = db_err.args[0].get("code")
            err_msg = db_err.args[0].get("message", err_msg)
            err_details = db_err.args[0].get("details")

        logger.error(
            "Database error querying profile for user_id=%s (code=%s, details=%s): %s",
            current_user.id,
            err_code,
            err_details,
            err_msg,
        )
        if "permission denied" in err_msg or "42501" in str(err_code) or "42501" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database permissions error accessing patient profile.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error querying profile: {err_msg}",
        )

    if not response or not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found. Please complete profile registration.",
        )

    profile = response.data[0]

    # Deduplicated audit logging for profile reads (15-minute sliding window)
    # Principle: Audit First, Cache Second
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)
    user_id_str = str(current_user.id)

    if profile_read_dedup.should_log(user_id_str):
        audit_service.log_security_event(
            client=client,
            action="patient_profile_read",
            entity_type="patient_profile",
            entity_id=str(profile["id"]),
            ip_address=client_ip,
            actor_user_id=current_user.id,
            user_agent=request.headers.get("user-agent"),
            details={
                "patient_id": profile["patient_id"],
                "read_reason": "direct_patient_access",
            },
            request_id=req_id,
        )
        profile_read_dedup.mark_logged(user_id_str)

    user_email = None
    if client:
        try:
            res_user = client.table("users").select("email").eq("id", str(current_user.id)).execute()
            if res_user.data and len(res_user.data) > 0:
                raw_email = res_user.data[0].get("email")
                if raw_email and not raw_email.endswith("@patient.internal"):
                    user_email = raw_email
        except Exception as e:
            logger.debug("Failed fetching user email: %s", e)

    if not user_email and current_user.email and not current_user.email.endswith("@patient.internal"):
        user_email = current_user.email

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
        email=user_email,
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
    Executes atomically in PostgreSQL alongside durable audit record generation.
    Rate-limited to prevent abuse.
    """
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)
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

    if not current_user.email and not current_user.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A verified phone number or email from authentication is required to register a patient profile.",
        )

    user_phone = normalize_phone(current_user.phone) if current_user.phone else None
    phone_checksum = hash_phone(user_phone) if user_phone else None
    candidate_patient_id = generate_patient_id()

    rpc_params = {
        "p_auth_user_id": str(current_user.id),
        "p_full_name": payload.full_name.strip(),
        "p_date_of_birth": str(payload.date_of_birth),
        "p_gender": payload.gender,
        "p_blood_group": payload.blood_group,
        "p_emergency_contact_phone": payload.emergency_contact_phone,
        "p_phone_e164": user_phone,
        "p_phone_hash": phone_checksum,
        "p_patient_id": candidate_patient_id,
        "p_ip_address": client_ip,
        "p_request_id": req_id,
    }

    try:
        res = client.rpc("register_patient_profile_atomic", rpc_params).execute()
        new_profile = res.data
    except Exception as e:
        err_msg = str(e)
        if "already associated" in err_msg or "unique_violation" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A medical profile is already associated with this verified phone number. Please log in or initiate account recovery if your number has changed.",
            )
        if "does not exist in authentication engine" in err_msg or "foreign_key_violation" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target user does not exist in authentication engine.",
            )
        if "unconfirmed" in err_msg or "insufficient_privilege" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A confirmed phone number or email in authentication engine is required to register a profile.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save patient profile: {err_msg}",
        )

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
        masked_aadhaar_ref=new_profile.get("masked_aadhaar_ref"),
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
    Executes atomically in PostgreSQL alongside durable audit record generation.
    """
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)
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

    rpc_params = {
        "p_auth_user_id": str(current_user.id),
        "p_blood_group": payload.blood_group,
        "p_emergency_contact_phone": payload.emergency_contact_phone,
        "p_ip_address": client_ip,
        "p_request_id": req_id,
    }

    try:
        res = client.rpc("update_patient_profile_atomic", rpc_params).execute()
        profile = res.data
    except Exception as e:
        err_msg = str(e)
        if "not found" in err_msg or "no_data_found" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient profile not found.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update patient profile: {err_msg}",
        )

    # If date_of_birth was provided in the update, persist it
    if payload.date_of_birth:
        try:
            update_data = {"date_of_birth": payload.date_of_birth.isoformat()}
            up_res = client.table("patient_profiles").update(update_data).eq("id", str(profile["id"])).execute()
            if up_res.data and len(up_res.data) > 0:
                profile["date_of_birth"] = up_res.data[0]["date_of_birth"]
            else:
                profile["date_of_birth"] = update_data["date_of_birth"]
        except Exception as dob_err:
            logger.warning("Could not update date_of_birth: %s", dob_err)

    user_email = None
    if client:
        try:
            res_user = client.table("users").select("email").eq("id", str(current_user.id)).execute()
            if res_user.data and len(res_user.data) > 0:
                raw_email = res_user.data[0].get("email")
                if raw_email and not raw_email.endswith("@patient.internal"):
                    user_email = raw_email
        except Exception:
            pass

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
        email=user_email,
        created_at=profile["created_at"],
        updated_at=profile.get("updated_at"),
        masked_aadhaar_ref=profile.get("masked_aadhaar_ref"),
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
    5. Failed demographic challenge attempts are durably audited without logging guessed values.
    """
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)
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
        # Audit failed challenge attempt without leaking whether profile exists
        audit_service.log_security_event(
            client=client,
            action="patient_recovery_challenge_failed",
            entity_type="patient_profile",
            entity_id="unknown",
            ip_address=client_ip,
            actor_user_id=current_user.id,
            user_agent=request.headers.get("user-agent"),
            details={
                "target_patient_id": payload.target_patient_id.strip(),
                "reason": "profile_not_found",
            },
            request_id=req_id,
        )
        raise invalid_challenge_err

    target = target_profile.data[0]

    # Prevent recovering an account already owned by caller
    if str(target["user_id"]) == str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your current session already owns this Patient ID.",
        )

    # 2. Verify identity challenge: DOB must match strictly
    mismatch = False
    if str(target["date_of_birth"]) != str(payload.challenge_date_of_birth):
        mismatch = True

    # If emergency contact is recorded, check secondary challenge
    if target.get("emergency_contact_phone") and payload.challenge_emergency_contact_phone:
        if target["emergency_contact_phone"].strip() != payload.challenge_emergency_contact_phone.strip():
            mismatch = True

    if mismatch:
        # Audit failed challenge without logging guessed challenge values!
        audit_service.log_security_event(
            client=client,
            action="patient_recovery_challenge_failed",
            entity_type="patient_profile",
            entity_id=str(target["id"]),
            ip_address=client_ip,
            actor_user_id=current_user.id,
            user_agent=request.headers.get("user-agent"),
            details={
                "target_patient_id": target["patient_id"],
                "reason": "demographic_mismatch",
            },
            request_id=req_id,
        )
        raise invalid_challenge_err

    # 3. Create recovery request in pending_institutional_approval state
    recovery_id = uuid4()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    caller_phone = normalize_phone(current_user.phone) if current_user.phone else "pending"
    client.table("patient_recovery_requests").insert({
        "id": str(recovery_id),
        "patient_profile_id": target["id"],
        "old_phone_hash": target["phone_hash"],
        "new_phone_e164": caller_phone,
        "recovery_channel": "hospital_desk_required",
        "status": "pending_institutional_approval",
        "expires_at": expires_at,
    }).execute()

    # Log recovery initiation in audit trail
    audit_service.log_security_event(
        client=client,
        action="patient_recovery_initiated",
        entity_type="patient_recovery_request",
        entity_id=str(recovery_id),
        ip_address=client_ip,
        actor_user_id=current_user.id,
        user_agent=request.headers.get("user-agent"),
        details={
            "target_patient_id": target["patient_id"],
            "recovery_channel": "hospital_desk_required",
        },
        request_id=req_id,
    )

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
    Executes atomically in PostgreSQL alongside durable audit record generation.
    """
    client_ip = get_client_ip(request)
    req_id = get_request_id(request)
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
        # Audit unauthorized completion attempt
        audit_service.log_security_event(
            client=client,
            action="patient_recovery_unauthorized_completion_attempt",
            entity_type="patient_recovery_request",
            entity_id=str(payload.recovery_request_id),
            ip_address=client_ip,
            actor_user_id=current_user.id,
            user_agent=request.headers.get("user-agent"),
            details={
                "current_status": req["status"],
                "reason": "unapproved_request_completion_blocked",
            },
            request_id=req_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Account recovery cannot be completed. Demographic knowledge alone is insufficient to authorize "
                "phone number transfer. An in-person hospital desk verification or approved administrative authorization "
                "is required to approve this request before profile transfer."
            ),
        )

    # 2. Call atomic recovery verification RPC
    if not current_user.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A verified phone number is required on the authenticated account to complete recovery.",
        )

    user_phone = normalize_phone(current_user.phone)
    new_phone_hash = hash_phone(user_phone)
    rpc_params = {
        "p_auth_user_id": str(current_user.id),
        "p_recovery_request_id": str(payload.recovery_request_id),
        "p_new_phone_hash": new_phone_hash,
        "p_ip_address": client_ip,
        "p_request_id": req_id,
    }

    try:
        res = client.rpc("verify_account_recovery_atomic", rpc_params).execute()
        result_data = res.data
    except Exception as e:
        err_msg = str(e)
        if "expired" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recovery request has expired.",
            )
        if "insufficient_privilege" in err_msg or "not match" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=err_msg,
            )
        if "unique_violation" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recovery verification failed: {err_msg}",
        )

    return AccountRecoveryVerifyResponse(
        success=True,
        patient_id=result_data.get("patient_id", ""),
        message=result_data.get("message", "Account successfully recovered. All medical records remain linked to your Patient ID."),
    )
