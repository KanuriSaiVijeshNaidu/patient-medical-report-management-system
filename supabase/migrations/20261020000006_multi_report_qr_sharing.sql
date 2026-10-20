-- ==============================================================================
-- Multi-Report QR Sharing Support Migration (Phase 3C)
-- Version: 20261020000006
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Implements atomic RPC create_multi_report_access_grant_atomic to allow
--      patients to bundle multiple selected medical reports into a single QR grant.
--   2. Updates validate_and_access_shared_report_atomic to return all authorized
--      reports within the grant while maintaining backward compatibility.
--   3. Enforces strict ownership checks: every report must belong to the caller.
--   4. Restricts execution privileges strictly to service_role and postgres.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. ATOMIC MULTI-REPORT SHARE GRANT CREATION RPC
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.create_multi_report_access_grant_atomic(
    p_auth_user_id UUID,
    p_report_ids UUID[],
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
    v_valid_report_ids UUID[];
    v_valid_report_codes TEXT[];
    v_grant_id UUID;
    v_expires_at TIMESTAMPTZ;
    v_actor_role VARCHAR(50);
    v_req_count INTEGER;
    v_found_count INTEGER;
BEGIN
    -- 1. Assert caller patient profile exists
    SELECT id INTO v_patient_profile_id
    FROM public.patient_profiles
    WHERE user_id = p_auth_user_id;

    IF v_patient_profile_id IS NULL THEN
        RAISE EXCEPTION 'Patient profile not found for authenticated user %.', p_auth_user_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 2. Validate report IDs array input
    IF p_report_ids IS NULL OR array_length(p_report_ids, 1) = 0 THEN
        RAISE EXCEPTION 'At least one medical report must be selected.'
            USING ERRCODE = 'check_violation';
    END IF;

    v_req_count := array_length(p_report_ids, 1);

    -- 3. Assert ALL requested reports exist and belong strictly to caller's patient profile
    SELECT 
        array_agg(r.id),
        array_agg(r.report_id)
    INTO 
        v_valid_report_ids,
        v_valid_report_codes
    FROM public.medical_reports r
    WHERE r.id = ANY(p_report_ids) AND r.patient_id = v_patient_profile_id;

    v_found_count := COALESCE(array_length(v_valid_report_ids, 1), 0);

    IF v_found_count = 0 OR v_found_count != v_req_count THEN
        RAISE EXCEPTION 'One or more medical reports not found or access denied.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 4. Validate expiration duration (between 60s and 86400s / 24h)
    IF p_expires_in_seconds < 60 OR p_expires_in_seconds > 86400 THEN
        RAISE EXCEPTION 'Expiry seconds must be between 60 and 86400 (received: %).', p_expires_in_seconds
            USING ERRCODE = 'check_violation';
    END IF;

    -- 5. Validate token hash format (64-character SHA-256 hex string)
    IF p_token_hash !~ '^[0-9a-fA-F]{64}$' THEN
        RAISE EXCEPTION 'Invalid token hash format. Expected 64-character SHA-256 hex string.'
            USING ERRCODE = 'check_violation';
    END IF;

    v_expires_at := NOW() + (p_expires_in_seconds || ' seconds')::INTERVAL;
    v_grant_id := gen_random_uuid();

    -- 6. Insert atomic grant record with all authorized report UUIDs
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
        v_valid_report_ids,
        0,
        v_expires_at,
        FALSE,
        NOW()
    );

    -- 7. Insert durable audit log in the same transaction
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
            'report_id', v_valid_report_codes[1],
            'report_ids', v_valid_report_codes,
            'reports_count', v_found_count,
            'expires_at', v_expires_at,
            'expiry_seconds', p_expires_in_seconds,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    RETURN jsonb_build_object(
        'grant_id', v_grant_id,
        'report_id', v_valid_report_codes[1],
        'report_ids', v_valid_report_codes,
        'reports_count', v_found_count,
        'expires_at', v_expires_at,
        'expires_in_seconds', p_expires_in_seconds
    );
END;
$$;

REVOKE ALL ON FUNCTION public.create_multi_report_access_grant_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_multi_report_access_grant_atomic TO service_role, postgres;

-- ------------------------------------------------------------------------------
-- 2. UPDATE ATOMIC VALIDATE AND ACCESS SHARED REPORT RPC
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
    v_reports_json JSONB;
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

    -- 5. Extract authorized report UUIDs
    IF v_grant.report_ids IS NULL OR array_length(v_grant.report_ids, 1) = 0 THEN
        RAISE EXCEPTION 'No authorized reports linked to this grant.'
            USING ERRCODE = 'no_data_found';
    END IF;

    v_report_target_uuid := v_grant.report_ids[1];

    -- 6. Fetch primary report metadata for backward compatibility
    SELECT id, report_id, title, category, report_date, file_storage_path, file_size_bytes, mime_type, verification_status
    INTO v_report
    FROM public.medical_reports
    WHERE id = v_report_target_uuid;

    IF v_report.id IS NULL THEN
        RAISE EXCEPTION 'Medical report record not found.'
            USING ERRCODE = 'no_data_found';
    END IF;

    -- 7. Fetch all authorized reports in this grant
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', r.id,
                'report_id', r.report_id,
                'title', r.title,
                'category', r.category,
                'report_date', r.report_date,
                'file_storage_path', r.file_storage_path,
                'file_size_bytes', r.file_size_bytes,
                'mime_type', r.mime_type,
                'verification_status', r.verification_status
            )
            ORDER BY r.created_at DESC
        ),
        '[]'::jsonb
    )
    INTO v_reports_json
    FROM public.medical_reports r
    WHERE r.id = ANY(v_grant.report_ids) AND r.patient_id = v_grant.patient_id;

    -- 8. Atomically increment access count
    v_new_access_count := v_grant.access_count + 1;
    UPDATE public.record_access_grants
    SET access_count = v_new_access_count
    WHERE id = v_grant.id;

    -- 9. Emit durable audit event for recipient access
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
            'report_ids', v_grant.report_ids,
            'access_count', v_new_access_count,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    -- 10. Return sanitized metadata and full reports array
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
        'access_count', v_new_access_count,
        'reports', v_reports_json
    );
END;
$$;

REVOKE ALL ON FUNCTION public.validate_and_access_shared_report_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.validate_and_access_shared_report_atomic TO service_role, postgres;
