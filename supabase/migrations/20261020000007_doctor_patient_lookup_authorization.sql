-- ==============================================================================
-- Doctor Patient Lookup & Hospital Authorization Migration (Phase 4A)
-- Version: 20261020000007
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Seeds default verified hospitals (City General Hospital and Metro Specialty Clinic).
--   2. Implements atomic RPC doctor_lookup_patient_reports_atomic for secure,
--      audited doctor search of patient medical records.
--   3. Enforces strict hospital authorization: only doctors whose hospital has an
--      active grant or issued the report can view patient medical records.
--   4. Links existing registered patient to City General Hospital to enable immediate
--      authorized vs. unauthorized institutional testing.
--   5. Restricts execution privileges strictly to service_role and postgres.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. SEED DEFAULT HOSPITALS
-- ------------------------------------------------------------------------------
INSERT INTO public.hospitals (
    id,
    registration_number,
    name,
    hospital_type,
    contact_phone,
    contact_email,
    address,
    verification_status,
    is_active,
    created_at
) VALUES 
    (
        '33333333-3333-3333-3333-333333333333',
        'HOSP-REG-4421',
        'City General Hospital',
        'general_hospital',
        '+911123456780',
        'contact@cityhospital.org',
        '{"city": "Mumbai", "state": "Maharashtra"}'::jsonb,
        'verified',
        TRUE,
        NOW()
    ),
    (
        '44444444-4444-4444-4444-444444444444',
        'HOSP-REG-9999',
        'Metro Specialty Clinic',
        'clinic',
        '+911123456799',
        'contact@metroclinic.org',
        '{"city": "Pune", "state": "Maharashtra"}'::jsonb,
        'verified',
        TRUE,
        NOW()
    )
ON CONFLICT (registration_number) DO UPDATE SET
    name = EXCLUDED.name,
    verification_status = 'verified',
    is_active = TRUE;

-- ------------------------------------------------------------------------------
-- 2. SEED ACTIVE ACCESS GRANT FOR PATIENT MED-2026-3N62YU -> CITY GENERAL HOSPITAL
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    v_pat_id UUID;
    v_hosp_id UUID := '33333333-3333-3333-3333-333333333333';
BEGIN
    SELECT id INTO v_pat_id FROM public.patient_profiles WHERE patient_id = 'MED-2026-3N62YU';
    IF v_pat_id IS NOT NULL THEN
        -- Only insert if active grant does not already exist
        IF NOT EXISTS (
            SELECT 1 FROM public.record_access_grants 
            WHERE patient_id = v_pat_id AND recipient_hospital_id = v_hosp_id AND is_revoked = FALSE
        ) THEN
            INSERT INTO public.record_access_grants (
                id,
                patient_id,
                recipient_hospital_id,
                grant_token_hash,
                scope,
                expires_at,
                is_revoked,
                created_at
            ) VALUES (
                gen_random_uuid(),
                v_pat_id,
                v_hosp_id,
                -- 64-char hex hash
                'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
                'all',
                NOW() + INTERVAL '365 days',
                FALSE,
                NOW()
            );
        END IF;
    END IF;
END $$;

-- ------------------------------------------------------------------------------
-- 3. ATOMIC DOCTOR PATIENT LOOKUP & AUTHORIZATION RPC
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.doctor_lookup_patient_reports_atomic(
    p_staff_user_id UUID,
    p_patient_id_code VARCHAR(32),
    p_ip_address VARCHAR(45),
    p_request_id VARCHAR(64)
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_staff RECORD;
    v_hospital RECORD;
    v_patient RECORD;
    v_is_authorized BOOLEAN := FALSE;
    v_reports_json JSONB;
    v_active_grant RECORD;
    v_grant_count INTEGER;
BEGIN
    -- 1. Assert caller is active hospital staff
    SELECT s.id, s.hospital_id, s.employee_id, s.role, s.department
    INTO v_staff
    FROM public.hospital_staff s
    WHERE s.user_id = p_staff_user_id AND s.is_active = TRUE;

    IF v_staff.id IS NULL THEN
        RAISE EXCEPTION 'Caller is not a verified, active hospital staff member.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 2. Assert hospital organization is verified and active
    SELECT h.id, h.name, h.registration_number
    INTO v_hospital
    FROM public.hospitals h
    WHERE h.id = v_staff.hospital_id AND h.verification_status = 'verified' AND h.is_active = TRUE;

    IF v_hospital.id IS NULL THEN
        RAISE EXCEPTION 'Staff member hospital organization is inactive or unverified.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 3. Lookup target patient profile by permanent Patient ID (MED-YYYY-XXXXXX)
    SELECT p.id, p.patient_id, p.full_name, p.gender, p.blood_group, p.date_of_birth
    INTO v_patient
    FROM public.patient_profiles p
    WHERE p.patient_id = p_patient_id_code;

    IF v_patient.id IS NULL THEN
        RAISE EXCEPTION 'Patient profile not found for Patient ID: %', p_patient_id_code
            USING ERRCODE = 'no_data_found';
    END IF;

    -- 4. Check Authorization:
    -- A: Active institutional grant issued by patient to this hospital
    SELECT g.id, g.scope, g.report_ids
    INTO v_active_grant
    FROM public.record_access_grants g
    WHERE g.patient_id = v_patient.id
      AND g.recipient_hospital_id = v_staff.hospital_id
      AND g.is_revoked = FALSE
      AND g.expires_at > NOW()
    ORDER BY g.created_at DESC
    LIMIT 1;

    IF v_active_grant.id IS NOT NULL THEN
        v_is_authorized := TRUE;
    END IF;

    -- B: Or hospital issued diagnostic reports for this patient
    IF NOT v_is_authorized THEN
        IF EXISTS (
            SELECT 1 FROM public.medical_reports r
            WHERE r.patient_id = v_patient.id AND r.hospital_id = v_staff.hospital_id
        ) THEN
            v_is_authorized := TRUE;
        END IF;
    END IF;

    -- If NOT authorized, log security audit event and raise exception
    IF NOT v_is_authorized THEN
        INSERT INTO public.audit_logs (
            actor_user_id,
            actor_role,
            action,
            entity_type,
            entity_id,
            ip_address,
            details
        ) VALUES (
            p_staff_user_id,
            'hospital_staff',
            'medical_report_access_denied',
            'patient_profile',
            v_patient.id::text,
            p_ip_address,
            jsonb_build_object(
                'patient_id', v_patient.patient_id,
                'hospital_id', v_hospital.id,
                'hospital_name', v_hospital.name,
                'reason', 'unauthorized_hospital_lookup_no_active_grant',
                'request_id', p_request_id,
                'outcome', 'denied'
            )
        );

        RAISE EXCEPTION 'Hospital % is not authorized to access records for Patient ID %.', v_hospital.name, p_patient_id_code
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 5. Fetch authorized reports for this patient
    IF v_active_grant.id IS NOT NULL AND v_active_grant.scope = 'specific_reports' THEN
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
                    'verification_status', r.verification_status,
                    'hospital_id', r.hospital_id
                )
                ORDER BY r.report_date DESC, r.created_at DESC
            ),
            '[]'::jsonb
        )
        INTO v_reports_json
        FROM public.medical_reports r
        WHERE r.patient_id = v_patient.id
          AND (r.id = ANY(v_active_grant.report_ids) OR r.hospital_id = v_staff.hospital_id);
    ELSE
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
                    'verification_status', r.verification_status,
                    'hospital_id', r.hospital_id
                )
                ORDER BY r.report_date DESC, r.created_at DESC
            ),
            '[]'::jsonb
        )
        INTO v_reports_json
        FROM public.medical_reports r
        WHERE r.patient_id = v_patient.id;
    END IF;

    -- 6. Log authorized lookup in audit_logs
    INSERT INTO public.audit_logs (
        actor_user_id,
        actor_role,
        action,
        entity_type,
        entity_id,
        ip_address,
        details
    ) VALUES (
        p_staff_user_id,
        'hospital_staff',
        'medical_report_read',
        'patient_profile',
        v_patient.id::text,
        p_ip_address,
        jsonb_build_object(
            'patient_id', v_patient.patient_id,
            'hospital_id', v_hospital.id,
            'hospital_name', v_hospital.name,
            'reports_count', jsonb_array_length(v_reports_json),
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    -- 7. Return patient confirmation details and authorized reports
    RETURN jsonb_build_object(
        'authorized', TRUE,
        'hospital_name', v_hospital.name,
        'hospital_id', v_hospital.id,
        'patient', jsonb_build_object(
            'patient_id', v_patient.patient_id,
            'full_name', v_patient.full_name,
            'gender', v_patient.gender,
            'blood_group', v_patient.blood_group,
            'date_of_birth', v_patient.date_of_birth
        ),
        'reports', v_reports_json
    );
END;
$$;

REVOKE ALL ON FUNCTION public.doctor_lookup_patient_reports_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.doctor_lookup_patient_reports_atomic TO service_role, postgres;
