-- ==============================================================================
-- Migration: 20261021000002_allow_photo_storage_paths_in_atomic_report_rpc.sql
-- Description:
--   1. Updates public.create_medical_report_atomic to allow photo formats:
--      - Storage path format: reports/<patient_profile_id>/<file_uuid>.(pdf|jpg|jpeg|png)
--      - MIME types: application/pdf, image/jpeg, image/png
--   2. Enforces storage path patient prefix matches the authenticated patient profile.
--   3. Cross-validates file extension against MIME type.
--   4. Preserves private storage, atomic audit log generation, and privilege restrictions.
-- ==============================================================================

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

    -- 4. Validate storage path syntax (reports/<patient_id>/<file_uuid>.<ext>)
    -- Supports .pdf, .jpg, .jpeg, and .png
    IF p_file_storage_path !~* '^reports/[0-9a-fA-F-]+/[0-9a-fA-F-]+\.(pdf|jpg|jpeg|png)$' THEN
        RAISE EXCEPTION 'Invalid storage path format.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 5. Enforce storage path belongs to the caller's patient profile
    IF p_file_storage_path !~* ('^reports/' || v_patient_profile_id::text || '/') THEN
        RAISE EXCEPTION 'Invalid storage path format: patient directory mismatch.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 6. Validate MIME type allowlist
    IF p_mime_type NOT IN ('application/pdf', 'image/jpeg', 'image/png') THEN
        RAISE EXCEPTION 'Only PDF, JPEG, and PNG documents are permitted for medical reports.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 7. Cross-validate extension matches MIME type
    IF (p_file_storage_path ~* '\.pdf$' AND p_mime_type != 'application/pdf') OR
       (p_file_storage_path ~* '\.(jpg|jpeg)$' AND p_mime_type != 'image/jpeg') OR
       (p_file_storage_path ~* '\.png$' AND p_mime_type != 'image/png') THEN
        RAISE EXCEPTION 'MIME type does not match storage path extension.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 8. Insert medical report record
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

    -- 9. Insert audit record in same transaction
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
