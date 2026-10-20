-- ==============================================================================
-- Secure QR-Based Medical Report Sharing Migration (Phase 3B)
-- Version: 20261020000002
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Expands record_security_audit_event action whitelist with share actions.
--   2. Enforces table privilege revocations on public.record_access_grants.
--   3. Implements atomic RPC create_report_access_grant_atomic for report sharing.
--   4. Implements atomic RPC revoke_report_access_grant_atomic for share revocation.
--   5. Implements atomic RPC validate_and_access_shared_report_atomic for recipient view.
--   6. Restricts RPC execute privileges strictly to service_role and postgres.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. EXPAND SECURITY AUDIT EVENT ACTION WHITELIST
-- ------------------------------------------------------------------------------
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
        'emergency_access_break_glass_executed',
        'medical_report_read',
        'medical_report_downloaded',
        'medical_report_access_denied',
        'medical_report_upload_failed',
        'report_share_created',
        'report_share_revoked',
        'report_share_accessed',
        'report_share_access_denied'
    ) THEN
        RAISE EXCEPTION 'Disallowed security audit action: %', p_action
            USING ERRCODE = 'check_violation';
    END IF;

    -- Resolve actor role from authoritative registry if actor_user_id is provided
    IF p_actor_user_id IS NOT NULL THEN
        SELECT role INTO v_actor_role FROM public.users WHERE id = p_actor_user_id;
    END IF;

    IF v_actor_role IS NULL THEN
        v_actor_role := 'anonymous';
    END IF;

    v_audit_id := gen_random_uuid();
    INSERT INTO public.audit_logs (
        id, actor_user_id, actor_role, action, entity_type, entity_id, ip_address, user_agent, details
    ) VALUES (
        v_audit_id, p_actor_user_id, v_actor_role, p_action, p_entity_type, p_entity_id,
        p_ip_address, p_user_agent, COALESCE(p_details, '{}'::jsonb)
    );

    RETURN v_audit_id;
END;
$$;

REVOKE ALL ON FUNCTION public.record_security_audit_event FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_security_audit_event TO service_role, postgres;

-- ------------------------------------------------------------------------------
-- 2. HARDEN TABLE PRIVILEGES ON public.record_access_grants
-- ------------------------------------------------------------------------------
REVOKE ALL ON public.record_access_grants FROM PUBLIC, anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.record_access_grants FROM authenticated;
GRANT SELECT ON public.record_access_grants TO authenticated;
GRANT ALL ON public.record_access_grants TO service_role, postgres;

CREATE INDEX IF NOT EXISTS idx_record_access_grants_patient_id ON public.record_access_grants(patient_id);

-- ------------------------------------------------------------------------------
-- 3. ATOMIC REPORT SHARE GRANT CREATION RPC
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.create_report_access_grant_atomic(
    p_auth_user_id UUID,
    p_report_id UUID,
    p_token_hash VARCHAR(64),
    p_expires_in_seconds INTEGER,
    p_ip_address VARCHAR(45),
    p_request_id VARCHAR(64)
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_patient_profile_id UUID;
    v_rep_id UUID;
    v_rep_code VARCHAR(32);
    v_grant_id UUID;
    v_expires_at TIMESTAMPTZ;
    v_actor_role VARCHAR(50);
BEGIN
    -- 1. Assert patient profile exists for authenticated user
    SELECT id INTO v_patient_profile_id
    FROM public.patient_profiles
    WHERE user_id = p_auth_user_id;

    IF v_patient_profile_id IS NULL THEN
        RAISE EXCEPTION 'Patient profile not found for authenticated user %.', p_auth_user_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 2. Assert medical report exists and belongs strictly to this patient
    SELECT id, report_id INTO v_rep_id, v_rep_code
    FROM public.medical_reports
    WHERE id = p_report_id AND patient_id = v_patient_profile_id;

    IF v_rep_id IS NULL THEN
        RAISE EXCEPTION 'Medical report not found or access denied.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 3. Validate expiration duration (between 60 seconds and 86400 seconds / 24 hours)
    IF p_expires_in_seconds < 60 OR p_expires_in_seconds > 86400 THEN
        RAISE EXCEPTION 'Expiry seconds must be between 60 and 86400 (received: %).', p_expires_in_seconds
            USING ERRCODE = 'check_violation';
    END IF;

    -- 4. Validate token hash format (64-character hex string)
    IF p_token_hash !~ '^[0-9a-fA-F]{64}$' THEN
        RAISE EXCEPTION 'Invalid token hash format. Expected 64-character SHA-256 hex string.'
            USING ERRCODE = 'check_violation';
    END IF;

    v_expires_at := NOW() + (p_expires_in_seconds || ' seconds')::INTERVAL;
    v_grant_id := gen_random_uuid();

    -- 5. Insert grant record
    INSERT INTO public.record_access_grants (
        id,
        patient_id,
        grant_token_hash,
        scope,
        report_ids,
        access_count,
        expires_at,
        is_revoked,
        created_at
    ) VALUES (
        v_grant_id,
        v_patient_profile_id,
        p_token_hash,
        'specific_reports',
        ARRAY[p_report_id],
        0,
        v_expires_at,
        FALSE,
        NOW()
    );

    -- 6. Insert durable audit log in the same transaction
    SELECT COALESCE(role, 'patient') INTO v_actor_role FROM public.users WHERE id = p_auth_user_id;
    INSERT INTO public.audit_logs (
        actor_user_id,
        actor_role,
        action,
        entity_type,
        entity_id,
        ip_address,
        details
    ) VALUES (
        p_auth_user_id,
        COALESCE(v_actor_role, 'patient'),
        'report_share_created',
        'record_access_grant',
        v_grant_id::text,
        p_ip_address,
        jsonb_build_object(
            'grant_id', v_grant_id,
            'report_id', v_rep_code,
            'expires_at', v_expires_at,
            'expiry_seconds', p_expires_in_seconds,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    RETURN jsonb_build_object(
        'grant_id', v_grant_id,
        'report_id', v_rep_code,
        'expires_at', v_expires_at,
        'expires_in_seconds', p_expires_in_seconds
    );
END;
$$;

REVOKE ALL ON FUNCTION public.create_report_access_grant_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_report_access_grant_atomic TO service_role, postgres;

-- ------------------------------------------------------------------------------
-- 4. ATOMIC REPORT SHARE GRANT REVOCATION RPC
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.revoke_report_access_grant_atomic(
    p_auth_user_id UUID,
    p_grant_id UUID,
    p_ip_address VARCHAR(45),
    p_request_id VARCHAR(64)
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_patient_profile_id UUID;
    v_grant RECORD;
    v_actor_role VARCHAR(50);
BEGIN
    -- 1. Assert patient profile exists for authenticated user
    SELECT id INTO v_patient_profile_id
    FROM public.patient_profiles
    WHERE user_id = p_auth_user_id;

    IF v_patient_profile_id IS NULL THEN
        RAISE EXCEPTION 'Patient profile not found for authenticated user.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 2. Select and lock grant row
    SELECT id, patient_id, is_revoked, report_ids INTO v_grant
    FROM public.record_access_grants
    WHERE id = p_grant_id AND patient_id = v_patient_profile_id
    FOR UPDATE;

    IF v_grant.id IS NULL THEN
        RAISE EXCEPTION 'Share grant not found or access denied.'
            USING ERRCODE = 'no_data_found';
    END IF;

    -- 3. Mark grant as revoked
    UPDATE public.record_access_grants
    SET is_revoked = TRUE,
        revoked_at = NOW()
    WHERE id = p_grant_id;

    -- 4. Insert durable audit log in the same transaction
    SELECT COALESCE(role, 'patient') INTO v_actor_role FROM public.users WHERE id = p_auth_user_id;
    INSERT INTO public.audit_logs (
        actor_user_id,
        actor_role,
        action,
        entity_type,
        entity_id,
        ip_address,
        details
    ) VALUES (
        p_auth_user_id,
        COALESCE(v_actor_role, 'patient'),
        'report_share_revoked',
        'record_access_grant',
        p_grant_id::text,
        p_ip_address,
        jsonb_build_object(
            'grant_id', p_grant_id,
            'report_ids', v_grant.report_ids,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    RETURN jsonb_build_object(
        'success', TRUE,
        'grant_id', p_grant_id,
        'revoked_at', NOW()
    );
END;
$$;

REVOKE ALL ON FUNCTION public.revoke_report_access_grant_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.revoke_report_access_grant_atomic TO service_role, postgres;

-- ------------------------------------------------------------------------------
-- 5. ATOMIC VALIDATE AND ACCESS SHARED REPORT RPC
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.validate_and_access_shared_report_atomic(
    p_token_hash VARCHAR(64),
    p_ip_address VARCHAR(45),
    p_request_id VARCHAR(64)
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_grant RECORD;
    v_report RECORD;
    v_report_target_uuid UUID;
    v_new_access_count INTEGER;
BEGIN
    -- 1. Validate token hash format
    IF p_token_hash !~ '^[0-9a-fA-F]{64}$' THEN
        RAISE EXCEPTION 'Invalid token hash format.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 2. Lookup and lock grant row by hash
    SELECT id, patient_id, scope, report_ids, access_count, expires_at, is_revoked
    INTO v_grant
    FROM public.record_access_grants
    WHERE grant_token_hash = p_token_hash
    FOR UPDATE;

    IF v_grant.id IS NULL THEN
        RAISE EXCEPTION 'Share grant not found.'
            USING ERRCODE = 'no_data_found';
    END IF;

    -- 3. Check revocation status
    IF v_grant.is_revoked THEN
        RAISE EXCEPTION 'Share grant has been revoked.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 4. Check expiration status
    IF v_grant.expires_at <= NOW() THEN
        RAISE EXCEPTION 'Share grant has expired.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 5. Extract single authorized report UUID
    IF v_grant.report_ids IS NULL OR array_length(v_grant.report_ids, 1) = 0 THEN
        RAISE EXCEPTION 'No authorized reports linked to this grant.'
            USING ERRCODE = 'no_data_found';
    END IF;

    v_report_target_uuid := v_grant.report_ids[1];

    -- 6. Fetch authorized report metadata
    SELECT id, report_id, title, category, report_date, file_storage_path, file_size_bytes, mime_type, verification_status
    INTO v_report
    FROM public.medical_reports
    WHERE id = v_report_target_uuid;

    IF v_report.id IS NULL THEN
        RAISE EXCEPTION 'Medical report record not found.'
            USING ERRCODE = 'no_data_found';
    END IF;

    -- 7. Atomically increment access count
    v_new_access_count := v_grant.access_count + 1;
    UPDATE public.record_access_grants
    SET access_count = v_new_access_count
    WHERE id = v_grant.id;

    -- 8. Emit durable audit event for recipient access
    INSERT INTO public.audit_logs (
        actor_user_id,
        actor_role,
        action,
        entity_type,
        entity_id,
        ip_address,
        details
    ) VALUES (
        NULL,
        'anonymous_recipient',
        'report_share_accessed',
        'medical_report',
        v_report.id::text,
        p_ip_address,
        jsonb_build_object(
            'grant_id', v_grant.id,
            'report_id', v_report.report_id,
            'access_count', v_new_access_count,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    -- 9. Return sanitized metadata and storage path (storage path is used by backend to issue short-lived signed URL)
    RETURN jsonb_build_object(
        'grant_id', v_grant.id,
        'report_id', v_report.report_id,
        'title', v_report.title,
        'category', v_report.category,
        'report_date', v_report.report_date,
        'file_storage_path', v_report.file_storage_path,
        'file_size_bytes', v_report.file_size_bytes,
        'mime_type', v_report.mime_type,
        'verification_status', v_report.verification_status,
        'share_expires_at', v_grant.expires_at,
        'access_count', v_new_access_count
    );
END;
$$;

REVOKE ALL ON FUNCTION public.validate_and_access_shared_report_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.validate_and_access_shared_report_atomic TO service_role, postgres;
