-- ==============================================================================
-- Secure Medical Reports Management Migration (Phase 3A)
-- Version: 20261020000001
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Configures private medical-reports Supabase storage bucket.
--   2. Updates record_security_audit_event action whitelist with report actions.
--   3. Implements atomic RPC create_medical_report_atomic for server-side report creation.
--   4. Implements atomic RPC delete_medical_report_atomic for server-side report deletion.
--   5. Restricts function execute privileges to service_role and postgres only.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. STORAGE BUCKET CONFIGURATION
-- ------------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('medical-reports', 'medical-reports', false, 26214400, ARRAY['application/pdf']::text[])
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = 26214400,
    allowed_mime_types = ARRAY['application/pdf']::text[];

-- ------------------------------------------------------------------------------
-- 2. EXPAND SECURITY AUDIT EVENT ACTION WHITELIST
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
        'medical_report_upload_failed'
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
-- 3. ATOMIC MEDICAL REPORT CREATION FUNCTION
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.create_medical_report_atomic(
    p_auth_user_id UUID,
    p_report_id VARCHAR(32),
    p_title VARCHAR(255),
    p_category VARCHAR(50),
    p_report_date DATE,
    p_file_storage_path TEXT,
    p_file_checksum_sha256 VARCHAR(64),
    p_file_size_bytes BIGINT,
    p_mime_type VARCHAR(100),
    p_metadata JSONB,
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
    v_report_uuid UUID;
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

    -- 2. Validate category
    IF p_category NOT IN ('blood_test', 'xray', 'ct_scan', 'mri', 'prescription', 'discharge_summary', 'other') THEN
        RAISE EXCEPTION 'Invalid report category: %', p_category
            USING ERRCODE = 'check_violation';
    END IF;

    -- 3. Validate report date cannot be future
    IF p_report_date > CURRENT_DATE THEN
        RAISE EXCEPTION 'Report date cannot be in the future.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 4. Validate storage path syntax (reports/<patient_id>/<file_uuid>.pdf)
    IF p_file_storage_path !~ '^reports/[0-9a-fA-F-]+/[0-9a-fA-F-]+\.pdf$' THEN
        RAISE EXCEPTION 'Invalid storage path format.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 5. Validate MIME type
    IF p_mime_type != 'application/pdf' THEN
        RAISE EXCEPTION 'Only PDF documents are permitted for medical reports.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 6. Insert medical report record
    v_report_uuid := gen_random_uuid();
    INSERT INTO public.medical_reports (
        id, report_id, patient_id, upload_source, title, category,
        report_date, file_storage_path, file_checksum_sha256,
        file_size_bytes, mime_type, verification_status, metadata
    ) VALUES (
        v_report_uuid, p_report_id, v_patient_profile_id, 'patient', p_title, p_category,
        p_report_date, p_file_storage_path, p_file_checksum_sha256,
        p_file_size_bytes, p_mime_type, 'unverified', COALESCE(p_metadata, '{}'::jsonb)
    );

    -- 7. Insert audit record in same transaction
    SELECT COALESCE(role, 'patient') INTO v_actor_role FROM public.users WHERE id = p_auth_user_id;
    INSERT INTO public.audit_logs (
        actor_user_id, actor_role, action, entity_type, entity_id, ip_address, details
    ) VALUES (
        p_auth_user_id, COALESCE(v_actor_role, 'patient'), 'medical_report_uploaded', 'medical_report', v_report_uuid::text, p_ip_address,
        jsonb_build_object(
            'report_id', p_report_id,
            'category', p_category,
            'report_date', p_report_date,
            'file_size_bytes', p_file_size_bytes,
            'mime_type', p_mime_type,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    RETURN jsonb_build_object(
        'id', v_report_uuid,
        'report_id', p_report_id,
        'patient_id', v_patient_profile_id,
        'upload_source', 'patient',
        'title', p_title,
        'category', p_category,
        'report_date', p_report_date,
        'file_size_bytes', p_file_size_bytes,
        'mime_type', p_mime_type,
        'verification_status', 'unverified',
        'metadata', COALESCE(p_metadata, '{}'::jsonb),
        'created_at', NOW()
    );
END;
$$;

REVOKE ALL ON FUNCTION public.create_medical_report_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_medical_report_atomic TO service_role, postgres;

-- ------------------------------------------------------------------------------
-- 4. ATOMIC MEDICAL REPORT DELETION FUNCTION
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.delete_medical_report_atomic(
    p_auth_user_id UUID,
    p_report_id UUID,
    p_ip_address VARCHAR(45),
    p_request_id VARCHAR(64)
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_report RECORD;
    v_actor_role VARCHAR(50);
BEGIN
    -- 1. Fetch report owned strictly by caller with row lock
    SELECT mr.* INTO v_report 
    FROM public.medical_reports mr
    JOIN public.patient_profiles pp ON pp.id = mr.patient_id
    WHERE mr.id = p_report_id AND pp.user_id = p_auth_user_id
    FOR UPDATE;

    IF v_report.id IS NULL THEN
        RAISE EXCEPTION 'Medical report not found or access denied.'
            USING ERRCODE = 'no_data_found';
    END IF;

    -- 2. Delete report record
    DELETE FROM public.medical_reports WHERE id = v_report.id;

    -- 3. Emit durable audit record
    SELECT COALESCE(role, 'patient') INTO v_actor_role FROM public.users WHERE id = p_auth_user_id;
    INSERT INTO public.audit_logs (
        actor_user_id, actor_role, action, entity_type, entity_id, ip_address, details
    ) VALUES (
        p_auth_user_id, COALESCE(v_actor_role, 'patient'), 'medical_report_deleted', 'medical_report', v_report.id::text, p_ip_address,
        jsonb_build_object(
            'report_id', v_report.report_id,
            'category', v_report.category,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    RETURN jsonb_build_object(
        'success', true,
        'file_storage_path', v_report.file_storage_path,
        'report_id', v_report.report_id
    );
END;
$$;

REVOKE ALL ON FUNCTION public.delete_medical_report_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.delete_medical_report_atomic TO service_role, postgres;
