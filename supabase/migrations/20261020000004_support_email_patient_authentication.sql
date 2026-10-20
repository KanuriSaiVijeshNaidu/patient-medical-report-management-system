-- ==============================================================================
-- Support Email Patient Authentication & Profile Creation
-- Version: 20261020000004
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Relaxes NOT NULL constraint on public.patient_profiles.phone_hash to allow
--      patients authenticating via email to register without a phone number.
--      Preserves unique index idx_patient_profiles_phone_hash_unique for phone users.
--   2. Updates public.patient_profiles.verification_status check constraint to include
--      'email_verified'.
--   3. Updates register_patient_profile_atomic to support both email and phone
--      authenticated accounts from auth.users, preserving full backward compatibility.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. RELAX NOT NULL ON phone_hash
-- ------------------------------------------------------------------------------
ALTER TABLE public.patient_profiles 
    ALTER COLUMN phone_hash DROP NOT NULL;

-- ------------------------------------------------------------------------------
-- 2. EXPAND VERIFICATION STATUS CHECK CONSTRAINT
-- ------------------------------------------------------------------------------
ALTER TABLE public.patient_profiles 
    DROP CONSTRAINT IF EXISTS patient_profiles_verification_status_check;

ALTER TABLE public.patient_profiles 
    ADD CONSTRAINT patient_profiles_verification_status_check 
    CHECK (verification_status IN ('unverified', 'phone_verified', 'email_verified', 'kyc_verified'));

-- ------------------------------------------------------------------------------
-- 3. UPDATED ATOMIC REGISTRATION FUNCTION SUPPORTING EMAIL & PHONE AUTH
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.register_patient_profile_atomic(
    p_auth_user_id UUID,
    p_full_name VARCHAR(150),
    p_date_of_birth DATE,
    p_gender VARCHAR(20),
    p_blood_group VARCHAR(5),
    p_emergency_contact_phone VARCHAR(20),
    p_phone_e164 VARCHAR(20),
    p_phone_hash VARCHAR(64),
    p_patient_id VARCHAR(32),
    p_ip_address VARCHAR(45),
    p_request_id VARCHAR(64)
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_profile_id UUID;
    v_existing_profile RECORD;
    v_actor_role VARCHAR(50);
    v_auth_phone TEXT;
    v_phone_confirmed_at TIMESTAMPTZ;
    v_auth_email TEXT;
    v_email_confirmed_at TIMESTAMPTZ;
    v_derived_phone_hash VARCHAR(64) := NULL;
    v_verification_status VARCHAR(32) := 'unverified';
BEGIN
    -- 1. Assert user exists in auth.users and fetch authoritative phone & email details
    SELECT phone, phone_confirmed_at, email, email_confirmed_at 
    INTO v_auth_phone, v_phone_confirmed_at, v_auth_email, v_email_confirmed_at 
    FROM auth.users WHERE id = p_auth_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target user % does not exist in authentication engine.', p_auth_user_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- 2. Validate authentication channel (Phone or Email)
    IF p_phone_e164 IS NOT NULL AND p_phone_e164 != '' THEN
        -- Phone-based registration path
        IF v_auth_phone IS NULL OR v_phone_confirmed_at IS NULL THEN
            RAISE EXCEPTION 'Authenticated user phone number is unconfirmed or missing in authentication engine.'
                USING ERRCODE = 'insufficient_privilege';
        END IF;

        IF regexp_replace(v_auth_phone, '^\+', '') IS DISTINCT FROM regexp_replace(p_phone_e164, '^\+', '') THEN
            RAISE EXCEPTION 'Submitted phone number does not match authenticated user phone.'
                USING ERRCODE = 'insufficient_privilege';
        END IF;

        v_derived_phone_hash := encode(sha256(p_phone_e164::bytea), 'hex');
        IF p_phone_hash IS NOT NULL AND p_phone_hash != '' AND p_phone_hash != v_derived_phone_hash THEN
            RAISE EXCEPTION 'Phone number and phone checksum do not match.'
                USING ERRCODE = 'check_violation';
        END IF;

        v_verification_status := 'phone_verified';
    ELSIF v_auth_email IS NOT NULL AND v_auth_email != '' THEN
        -- Email-based registration path
        v_derived_phone_hash := NULL;
        v_verification_status := 'email_verified';
    ELSE
        RAISE EXCEPTION 'Authenticated account must have a verified email or phone number.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 3. Ensure record exists in public.users without modifying role if already set
    INSERT INTO public.users (id, email, phone_e164, role, is_active)
    VALUES (p_auth_user_id, v_auth_email, p_phone_e164, 'patient', TRUE)
    ON CONFLICT (id) DO UPDATE 
        SET email = COALESCE(EXCLUDED.email, public.users.email),
            phone_e164 = COALESCE(EXCLUDED.phone_e164, public.users.phone_e164)
        WHERE public.users.role = 'patient';

    SELECT role INTO v_actor_role FROM public.users WHERE id = p_auth_user_id;
    IF v_actor_role IS NULL THEN
        v_actor_role := 'patient';
    END IF;

    -- 4. Idempotency Check: Return existing profile if already registered
    SELECT * INTO v_existing_profile FROM public.patient_profiles WHERE user_id = p_auth_user_id;
    IF v_existing_profile.id IS NOT NULL THEN
        RETURN jsonb_build_object(
            'status', 'existing',
            'id', v_existing_profile.id,
            'patient_id', v_existing_profile.patient_id,
            'full_name', v_existing_profile.full_name,
            'date_of_birth', v_existing_profile.date_of_birth,
            'gender', v_existing_profile.gender,
            'blood_group', v_existing_profile.blood_group,
            'emergency_contact_phone', v_existing_profile.emergency_contact_phone,
            'verification_status', v_existing_profile.verification_status,
            'created_at', v_existing_profile.created_at,
            'updated_at', v_existing_profile.updated_at
        );
    END IF;

    -- 5. Unique Phone Hash Check (only if phone is supplied)
    IF v_derived_phone_hash IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM public.patient_profiles WHERE phone_hash = v_derived_phone_hash) THEN
            RAISE EXCEPTION 'A medical profile is already associated with this verified phone number.'
                USING ERRCODE = 'unique_violation';
        END IF;
    END IF;

    -- 6. Insert new profile
    v_profile_id := gen_random_uuid();
    INSERT INTO public.patient_profiles (
        id, patient_id, user_id, full_name, date_of_birth, gender, blood_group,
        emergency_contact_phone, phone_hash, verification_status
    ) VALUES (
        v_profile_id, p_patient_id, p_auth_user_id, p_full_name, p_date_of_birth, p_gender, p_blood_group,
        p_emergency_contact_phone, v_derived_phone_hash, v_verification_status
    );

    -- 7. Insert audit record in same transaction
    INSERT INTO public.audit_logs (
        actor_user_id, actor_role, action, entity_type, entity_id, ip_address, details
    ) VALUES (
        p_auth_user_id, v_actor_role, 'patient_profile_created', 'patient_profile', v_profile_id::text, p_ip_address,
        jsonb_build_object(
            'patient_id', p_patient_id,
            'verification_channel', CASE WHEN v_derived_phone_hash IS NOT NULL THEN 'phone' ELSE 'email' END,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    RETURN jsonb_build_object(
        'status', 'created',
        'id', v_profile_id,
        'patient_id', p_patient_id,
        'full_name', p_full_name,
        'date_of_birth', p_date_of_birth,
        'gender', p_gender,
        'blood_group', p_blood_group,
        'emergency_contact_phone', p_emergency_contact_phone,
        'verification_status', v_verification_status,
        'created_at', NOW()
    );
END;
$$;

REVOKE ALL ON FUNCTION public.register_patient_profile_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_patient_profile_atomic TO service_role, postgres;
