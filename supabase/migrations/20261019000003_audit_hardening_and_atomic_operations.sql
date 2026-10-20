-- ==============================================================================
-- Audit Hardening, Atomic Operations, and Mutation Isolation Migration
-- Version: 20261019000003
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Revoke client INSERT privileges on public.audit_logs and restrict SELECT to platform_admin.
--   2. Deny direct client mutations on patient_profiles, users, record_access_grants, emergency_access_logs.
--   3. Implement atomic, operation-specific database functions:
--      - register_patient_profile_atomic
--      - update_patient_profile_atomic
--      - verify_account_recovery_atomic
--      - record_security_audit_event
--   4. Strictly restrict function EXECUTE to service_role and postgres only.
--   5. Add functional index on audit_logs.details->>'request_id'.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. AUDIT LOGS PRIVILEGES & POLICY HARDENING
-- ------------------------------------------------------------------------------
-- Revoke direct table mutation grants from untrusted roles
REVOKE ALL ON public.audit_logs FROM anon, PUBLIC;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.audit_logs FROM authenticated;
GRANT SELECT ON public.audit_logs TO authenticated;

-- Drop permissive client insertion policy
DROP POLICY IF EXISTS "Authenticated users insert audit logs" ON public.audit_logs;

-- Restrict audit-log reads strictly to active platform administrators
DROP POLICY IF EXISTS "Admins view audit logs" ON public.audit_logs;
CREATE POLICY "Admins view audit logs"
    ON public.audit_logs FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.users 
            WHERE id = auth.uid() AND role = 'platform_admin' AND is_active = TRUE
        )
    );

-- Functional index for correlation lookup
CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id ON public.audit_logs ((details->>'request_id'));

-- ------------------------------------------------------------------------------
-- 2. DENY DIRECT POSTGREST CLIENT MUTATIONS ON DOMAIN TABLES
-- ------------------------------------------------------------------------------
-- patient_profiles: Revoke direct client INSERT and UPDATE
DROP POLICY IF EXISTS "Patients insert own profile" ON public.patient_profiles;
DROP POLICY IF EXISTS "Patients update own profile" ON public.patient_profiles;
-- Retain SELECT: Patients can view their own profile via PostgREST or Backend
-- (Policy "Patients view own profile" USING (auth.uid() = user_id) remains active)

-- users: Revoke direct client INSERT and UPDATE
DROP POLICY IF EXISTS "Users insert own record" ON public.users;
DROP POLICY IF EXISTS "Users update own record" ON public.users;
-- Retain SELECT: Users can view their own record via PostgREST or Backend
-- (Policy "Users view own record" USING (auth.uid() = id) remains active)

-- record_access_grants: Revoke direct client ALL; restrict to SELECT only
DROP POLICY IF EXISTS "Patients manage own access grants" ON public.record_access_grants;
DROP POLICY IF EXISTS "Patients view own access grants" ON public.record_access_grants;
CREATE POLICY "Patients view own access grants"
    ON public.record_access_grants FOR SELECT
    USING (
        patient_id IN (
            SELECT id FROM public.patient_profiles WHERE user_id = auth.uid()
        )
    );

-- emergency_access_logs: Revoke direct client INSERT
DROP POLICY IF EXISTS "Hospital staff insert emergency access" ON public.emergency_access_logs;
DROP POLICY IF EXISTS "Hospital staff view own emergency access" ON public.emergency_access_logs;
CREATE POLICY "Hospital staff view own emergency access"
    ON public.emergency_access_logs FOR SELECT
    USING (
        accessed_by_staff_id IN (
            SELECT id FROM public.hospital_staff WHERE user_id = auth.uid() AND is_active = TRUE
        )
    );

-- patient_recovery_requests: Expand status constraint to include approved_by_staff and completed
ALTER TABLE public.patient_recovery_requests DROP CONSTRAINT IF EXISTS patient_recovery_requests_status_check;
ALTER TABLE public.patient_recovery_requests ADD CONSTRAINT patient_recovery_requests_status_check 
    CHECK (status IN ('pending', 'verified', 'approved_by_staff', 'completed', 'rejected'));

-- ------------------------------------------------------------------------------
-- 3. NARROW, ATOMIC SENSITIVE OPERATION FUNCTIONS
-- ------------------------------------------------------------------------------

-- FUNCTION 1: Atomic Patient Profile Registration
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
    v_derived_phone_hash VARCHAR(64);
BEGIN
    -- 1. Assert user exists in auth.users and fetch authoritative phone & confirmed status
    SELECT phone, phone_confirmed_at INTO v_auth_phone, v_phone_confirmed_at 
    FROM auth.users WHERE id = p_auth_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target user % does not exist in authentication engine.', p_auth_user_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- 2. Assert phone number is supplied
    IF p_phone_e164 IS NULL OR p_phone_e164 = '' THEN
        RAISE EXCEPTION 'A verified phone number is required to register a patient profile.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 3. Assert user phone has been confirmed in authentication engine
    IF v_auth_phone IS NULL OR v_phone_confirmed_at IS NULL THEN
        RAISE EXCEPTION 'Authenticated user phone number is unconfirmed or missing in authentication engine.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 4. Assert phone number matches auth.users
    IF regexp_replace(v_auth_phone, '^\+', '') IS DISTINCT FROM regexp_replace(p_phone_e164, '^\+', '') THEN
        RAISE EXCEPTION 'Submitted phone number does not match authenticated user phone.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 5. Cryptographic Phone Hash Integrity Check
    v_derived_phone_hash := encode(sha256(p_phone_e164::bytea), 'hex');
    IF p_phone_hash != v_derived_phone_hash THEN
        RAISE EXCEPTION 'Phone number and phone checksum do not match.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 5. Ensure record exists in public.users without modifying role if already set
    INSERT INTO public.users (id, phone_e164, role, is_active)
    VALUES (p_auth_user_id, p_phone_e164, 'patient', TRUE)
    ON CONFLICT (id) DO UPDATE 
        SET phone_e164 = EXCLUDED.phone_e164
        WHERE public.users.role = 'patient';

    SELECT role INTO v_actor_role FROM public.users WHERE id = p_auth_user_id;
    IF v_actor_role IS NULL THEN
        v_actor_role := 'patient';
    END IF;

    -- 6. Idempotency Check: Return existing profile if already registered
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

    -- 7. Unique Phone Hash Check across other profiles
    IF EXISTS (SELECT 1 FROM public.patient_profiles WHERE phone_hash = v_derived_phone_hash) THEN
        RAISE EXCEPTION 'A medical profile is already associated with this verified phone number.'
            USING ERRCODE = 'unique_violation';
    END IF;

    -- 8. Insert new profile
    v_profile_id := gen_random_uuid();
    INSERT INTO public.patient_profiles (
        id, patient_id, user_id, full_name, date_of_birth, gender, blood_group,
        emergency_contact_phone, phone_hash, verification_status
    ) VALUES (
        v_profile_id, p_patient_id, p_auth_user_id, p_full_name, p_date_of_birth, p_gender, p_blood_group,
        p_emergency_contact_phone, v_derived_phone_hash, 'phone_verified'
    );

    -- 9. Insert audit record in same transaction
    INSERT INTO public.audit_logs (
        actor_user_id, actor_role, action, entity_type, entity_id, ip_address, details
    ) VALUES (
        p_auth_user_id, v_actor_role, 'patient_profile_created', 'patient_profile', v_profile_id::text, p_ip_address,
        jsonb_build_object('patient_id', p_patient_id, 'request_id', p_request_id, 'outcome', 'success')
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
        'verification_status', 'phone_verified',
        'created_at', NOW()
    );
END;
$$;

REVOKE ALL ON FUNCTION public.register_patient_profile_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_patient_profile_atomic TO service_role, postgres;


-- FUNCTION 2: Atomic Patient Profile Update
CREATE OR REPLACE FUNCTION public.update_patient_profile_atomic(
    p_auth_user_id UUID,
    p_blood_group VARCHAR(5),
    p_emergency_contact_phone VARCHAR(20),
    p_ip_address VARCHAR(45),
    p_request_id VARCHAR(64)
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_profile RECORD;
    v_actor_role VARCHAR(50);
    v_updated_fields TEXT[] := '{}';
BEGIN
    -- 1. Fetch profile owned strictly by caller with row lock
    SELECT * INTO v_profile FROM public.patient_profiles WHERE user_id = p_auth_user_id FOR UPDATE;
    IF v_profile.id IS NULL THEN
        RAISE EXCEPTION 'Patient profile not found for user %.', p_auth_user_id
            USING ERRCODE = 'no_data_found';
    END IF;

    SELECT role INTO v_actor_role FROM public.users WHERE id = p_auth_user_id;
    IF v_actor_role IS NULL THEN
        v_actor_role := 'patient';
    END IF;

    -- 2. Apply non-identity clinical updates
    IF p_blood_group IS NOT NULL AND p_blood_group IS DISTINCT FROM v_profile.blood_group THEN
        UPDATE public.patient_profiles SET blood_group = p_blood_group WHERE id = v_profile.id;
        v_updated_fields := array_append(v_updated_fields, 'blood_group');
    END IF;

    IF p_emergency_contact_phone IS NOT NULL AND p_emergency_contact_phone IS DISTINCT FROM v_profile.emergency_contact_phone THEN
        UPDATE public.patient_profiles SET emergency_contact_phone = p_emergency_contact_phone WHERE id = v_profile.id;
        v_updated_fields := array_append(v_updated_fields, 'emergency_contact_phone');
    END IF;

    UPDATE public.patient_profiles SET updated_at = NOW() WHERE id = v_profile.id;

    -- 3. Emit audit record in same transaction
    INSERT INTO public.audit_logs (
        actor_user_id, actor_role, action, entity_type, entity_id, ip_address, details
    ) VALUES (
        p_auth_user_id, v_actor_role, 'patient_profile_updated', 'patient_profile', v_profile.id::text, p_ip_address,
        jsonb_build_object('updated_fields', v_updated_fields, 'request_id', p_request_id, 'outcome', 'success')
    );

    SELECT * INTO v_profile FROM public.patient_profiles WHERE id = v_profile.id;
    RETURN jsonb_build_object(
        'id', v_profile.id,
        'patient_id', v_profile.patient_id,
        'full_name', v_profile.full_name,
        'date_of_birth', v_profile.date_of_birth,
        'gender', v_profile.gender,
        'blood_group', v_profile.blood_group,
        'emergency_contact_phone', v_profile.emergency_contact_phone,
        'verification_status', v_profile.verification_status,
        'updated_at', v_profile.updated_at
    );
END;
$$;

REVOKE ALL ON FUNCTION public.update_patient_profile_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.update_patient_profile_atomic TO service_role, postgres;


-- FUNCTION 3: Atomic Account Recovery Verification
CREATE OR REPLACE FUNCTION public.verify_account_recovery_atomic(
    p_auth_user_id UUID,
    p_recovery_request_id UUID,
    p_new_phone_hash VARCHAR(64),
    p_ip_address VARCHAR(45),
    p_request_id VARCHAR(64)
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_req RECORD;
    v_profile RECORD;
    v_new_user RECORD;
    v_actor_role VARCHAR(50);
    v_auth_phone TEXT;
    v_phone_confirmed_at TIMESTAMPTZ;
    v_derived_phone_hash VARCHAR(64);
BEGIN
    -- 1. Fetch recovery request WITH ROW LOCK to prevent concurrent completion replays
    SELECT * INTO v_req FROM public.patient_recovery_requests 
    WHERE id = p_recovery_request_id FOR UPDATE;
    
    IF v_req.id IS NULL THEN
        RAISE EXCEPTION 'Recovery request % not found.', p_recovery_request_id
            USING ERRCODE = 'no_data_found';
    END IF;

    -- 2. State & Replay Check
    IF v_req.status != 'approved_by_staff' THEN
        RAISE EXCEPTION 'Recovery request has not been approved by hospital desk verification or has already been completed.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 3. Expiration Check
    IF v_req.expires_at <= NOW() THEN
        RAISE EXCEPTION 'Recovery request has expired.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 4. Verified New Account in auth.users & phone confirmation
    SELECT phone, phone_confirmed_at INTO v_auth_phone, v_phone_confirmed_at 
    FROM auth.users WHERE id = p_auth_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target user % does not exist in authentication engine.', p_auth_user_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- 5. Assert caller phone has been confirmed in authentication engine
    IF v_auth_phone IS NULL OR v_phone_confirmed_at IS NULL THEN
        RAISE EXCEPTION 'Authenticated caller phone number is unconfirmed or missing in authentication engine.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 6. Verified Phone Number Matching against auth.users
    IF regexp_replace(v_auth_phone, '^\+', '') IS DISTINCT FROM regexp_replace(v_req.new_phone_e164, '^\+', '') THEN
        RAISE EXCEPTION 'Authenticated account phone does not match approved recovery phone.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 6. Ensure caller row exists in public.users WITH ROW LOCK
    SELECT * INTO v_new_user FROM public.users WHERE id = p_auth_user_id FOR UPDATE;
    IF v_new_user.id IS NULL THEN
        INSERT INTO public.users (id, phone_e164, role, is_active)
        VALUES (p_auth_user_id, v_req.new_phone_e164, 'patient', TRUE)
        ON CONFLICT (id) DO UPDATE SET phone_e164 = EXCLUDED.phone_e164
        RETURNING * INTO v_new_user;
    END IF;

    -- 7. Verified Phone Number Matching against public.users
    IF v_req.new_phone_e164 IS DISTINCT FROM v_new_user.phone_e164 THEN
        RAISE EXCEPTION 'Verified caller phone number does not match approved recovery phone number.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 8. Prevent caller from already owning another distinct profile
    IF EXISTS (
        SELECT 1 FROM public.patient_profiles 
        WHERE user_id = p_auth_user_id AND id != v_req.patient_profile_id
    ) THEN
        RAISE EXCEPTION 'Authenticated account already owns another patient profile.'
            USING ERRCODE = 'unique_violation';
    END IF;

    -- 9. Authoritative derivation of phone hash in SQL (caller cannot forge)
    v_derived_phone_hash := encode(sha256(v_req.new_phone_e164::bytea), 'hex');
    IF p_new_phone_hash IS NOT NULL AND p_new_phone_hash != '' AND p_new_phone_hash != v_derived_phone_hash THEN
        RAISE EXCEPTION 'Phone checksum mismatch.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 10. Unique Phone Hash Collision Check on other profiles
    IF EXISTS (
        SELECT 1 FROM public.patient_profiles 
        WHERE phone_hash = v_derived_phone_hash AND id != v_req.patient_profile_id
    ) THEN
        RAISE EXCEPTION 'Target phone number is already registered to another patient profile.'
            USING ERRCODE = 'unique_violation';
    END IF;

    -- 11. Lock target patient profile
    SELECT * INTO v_profile FROM public.patient_profiles 
    WHERE id = v_req.patient_profile_id FOR UPDATE;

    SELECT role INTO v_actor_role FROM public.users WHERE id = p_auth_user_id;
    IF v_actor_role IS NULL THEN
        v_actor_role := 'patient';
    END IF;

    -- 12. Re-link profile to new authenticated account with authoritative phone hash
    UPDATE public.patient_profiles 
    SET user_id = p_auth_user_id, phone_hash = v_derived_phone_hash, updated_at = NOW()
    WHERE id = v_req.patient_profile_id;

    -- 13. Mark request completed
    UPDATE public.patient_recovery_requests SET status = 'completed' WHERE id = v_req.id;

    -- 14. Emit audit record in same transaction
    INSERT INTO public.audit_logs (
        actor_user_id, actor_role, action, entity_type, entity_id, ip_address, details
    ) VALUES (
        p_auth_user_id, v_actor_role, 'patient_account_recovered', 'patient_profile', v_req.patient_profile_id::text, p_ip_address,
        jsonb_build_object(
            'recovery_request_id', p_recovery_request_id,
            'old_phone_hash', v_req.old_phone_hash,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    RETURN jsonb_build_object(
        'success', true,
        'patient_id', v_profile.patient_id,
        'message', 'Account successfully recovered. All medical records remain linked to your Patient ID.'
    );
END;
$$;

REVOKE ALL ON FUNCTION public.verify_account_recovery_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.verify_account_recovery_atomic TO service_role, postgres;


-- FUNCTION 4: Atomic Security & Read Audit Logging
CREATE OR REPLACE FUNCTION public.record_security_audit_event(
    p_actor_user_id UUID,
    p_action VARCHAR(100),
    p_entity_type VARCHAR(50),
    p_entity_id VARCHAR(100),
    p_ip_address VARCHAR(45),
    p_user_agent TEXT,
    p_details JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_audit_id UUID;
    v_actor_role VARCHAR(50);
BEGIN
    -- Action whitelist check
    IF p_action NOT IN (
        'patient_profile_read',
        'patient_recovery_initiated',
        'patient_recovery_challenge_failed',
        'patient_recovery_unauthorized_completion_attempt',
        'security_rate_limit_exceeded',
        'emergency_access_break_glass_executed'
    ) THEN
        RAISE EXCEPTION 'Disallowed security audit action: %', p_action
            USING ERRCODE = 'check_violation';
    END IF;

    -- Resolve actor role from authoritative registry if actor_user_id is provided
    IF p_actor_user_id IS NOT NULL THEN
        SELECT role INTO v_actor_role FROM public.users WHERE id = p_actor_user_id;
        IF v_actor_role IS NULL THEN
            v_actor_role := 'patient';
        END IF;
    ELSE
        v_actor_role := 'anon';
    END IF;

    v_audit_id := gen_random_uuid();
    INSERT INTO public.audit_logs (
        id, actor_user_id, actor_role, action, entity_type, entity_id, ip_address, user_agent, details
    ) VALUES (
        v_audit_id, p_actor_user_id, v_actor_role, p_action, p_entity_type, p_entity_id, p_ip_address, p_user_agent, p_details
    );

    RETURN v_audit_id;
END;
$$;

REVOKE ALL ON FUNCTION public.record_security_audit_event FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_security_audit_event TO service_role, postgres;
