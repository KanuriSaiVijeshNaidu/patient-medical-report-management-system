-- ==============================================================================
-- TEST SUITE: Secure Medical Reports Management Integration Tests
-- Tests executed directly against local Supabase PostgreSQL (127.0.0.1:54322)
-- ==============================================================================

\set ON_ERROR_STOP on
\echo '=== Starting Secure Medical Reports Management Integration Test Suite ==='

DO $$
DECLARE
    v_patient_user_a UUID := '88888888-8888-8888-8888-888888888881'::UUID;
    v_patient_user_b UUID := '88888888-8888-8888-8888-888888888882'::UUID;
    v_profile_a_id UUID := '77777777-7777-7777-7777-777777777771'::UUID;
    v_profile_b_id UUID := '77777777-7777-7777-7777-777777777772'::UUID;
    v_report_res JSONB;
    v_delete_res JSONB;
    v_report_uuid UUID;
    v_audit_count INT;
    v_test_count INT := 0;
    v_pass_count INT := 0;
    v_bucket_public BOOLEAN;
    v_bucket_mimes TEXT[];
BEGIN
    RAISE NOTICE '--- 1. Testing Storage Bucket Configuration ---';
    v_test_count := v_test_count + 1;
    SELECT public, allowed_mime_types INTO v_bucket_public, v_bucket_mimes
    FROM storage.buckets
    WHERE id = 'medical-reports';

    IF v_bucket_public = FALSE AND v_bucket_mimes = ARRAY['application/pdf']::TEXT[] THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [1]: medical-reports bucket is private and strictly restricted to application/pdf';
    ELSE
        RAISE EXCEPTION 'FAIL [1]: medical-reports bucket config invalid (public=%, mimes=%)', v_bucket_public, v_bucket_mimes;
    END IF;

    RAISE NOTICE '--- 2. Testing RPC Privilege Revocation from authenticated / anon ---';
    -- create_medical_report_atomic
    v_test_count := v_test_count + 1;
    IF has_function_privilege('authenticated', 'public.create_medical_report_atomic(uuid,varchar,varchar,varchar,date,text,varchar,bigint,varchar,jsonb,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('anon', 'public.create_medical_report_atomic(uuid,varchar,varchar,varchar,date,text,varchar,bigint,varchar,jsonb,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('service_role', 'public.create_medical_report_atomic(uuid,varchar,varchar,varchar,date,text,varchar,bigint,varchar,jsonb,varchar,varchar)', 'EXECUTE') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [2]: create_medical_report_atomic is executable ONLY by service_role/postgres';
    ELSE
        RAISE EXCEPTION 'FAIL [2]: create_medical_report_atomic has overly broad execute privileges';
    END IF;

    -- delete_medical_report_atomic
    v_test_count := v_test_count + 1;
    IF has_function_privilege('authenticated', 'public.delete_medical_report_atomic(uuid,uuid,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('anon', 'public.delete_medical_report_atomic(uuid,uuid,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('service_role', 'public.delete_medical_report_atomic(uuid,uuid,varchar,varchar)', 'EXECUTE') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [3]: delete_medical_report_atomic is executable ONLY by service_role/postgres';
    ELSE
        RAISE EXCEPTION 'FAIL [3]: delete_medical_report_atomic has overly broad execute privileges';
    END IF;

    RAISE NOTICE '--- 3. Setting Up Test Fixtures ---';
    -- Clean up previous test artifacts if any
    DELETE FROM public.medical_reports WHERE report_id LIKE 'REP-2026-%';
    DELETE FROM public.patient_profiles WHERE user_id IN (v_patient_user_a, v_patient_user_b);
    DELETE FROM public.users WHERE id IN (v_patient_user_a, v_patient_user_b);
    DELETE FROM auth.users WHERE id IN (v_patient_user_a, v_patient_user_b);

    INSERT INTO auth.users (id, instance_id, aud, role, email, phone, phone_confirmed_at, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, is_super_admin, created_at, updated_at)
    VALUES
        (v_patient_user_a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'test_rep_a@example.com', '+919876543201', NOW(), 'enc', NOW(), '{"provider":"phone"}', '{}', FALSE, NOW(), NOW()),
        (v_patient_user_b, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'test_rep_b@example.com', '+919876543202', NOW(), 'enc', NOW(), '{"provider":"phone"}', '{}', FALSE, NOW(), NOW());

    SELECT (public.register_patient_profile_atomic(
        v_patient_user_a, 'Patient A', '1990-01-01'::DATE, 'male', 'O+',
        '+919876543201', '+919876543201', encode(sha256('+919876543201'::bytea), 'hex'),
        'MED-2026-AAAA01', '127.0.0.1', 'req-setup-a'
    )->>'id')::UUID INTO v_profile_a_id;

    SELECT (public.register_patient_profile_atomic(
        v_patient_user_b, 'Patient B', '1992-02-02'::DATE, 'female', 'A+',
        '+919876543202', '+919876543202', encode(sha256('+919876543202'::bytea), 'hex'),
        'MED-2026-BBBB02', '127.0.0.1', 'req-setup-b'
    )->>'id')::UUID INTO v_profile_b_id;

    RAISE NOTICE '--- 4. Testing Validation Checks in create_medical_report_atomic ---';
    -- Future date validation
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.create_medical_report_atomic(
            p_auth_user_id := v_patient_user_a,
            p_report_id := 'REP-2026-FUT001',
            p_title := 'Future Report',
            p_category := 'blood_test',
            p_report_date := (CURRENT_DATE + INTERVAL '5 days')::DATE,
            p_file_storage_path := 'reports/' || v_profile_a_id::text || '/' || gen_random_uuid()::text || '.pdf',
            p_file_checksum_sha256 := repeat('a', 64),
            p_file_size_bytes := 1024,
            p_mime_type := 'application/pdf',
            p_metadata := '{}'::jsonb,
            p_ip_address := '127.0.0.1',
            p_request_id := 'req-fut'
        );
        RAISE EXCEPTION 'FAIL [4]: Future report_date was permitted!';
    EXCEPTION
        WHEN check_violation THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [4]: Future report_date rejected by RPC check';
    END;

    -- Non-PDF MIME type validation
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.create_medical_report_atomic(
            p_auth_user_id := v_patient_user_a,
            p_report_id := 'REP-2026-BAD001',
            p_title := 'Bad Mime Report',
            p_category := 'blood_test',
            p_report_date := CURRENT_DATE,
            p_file_storage_path := 'reports/' || v_profile_a_id::text || '/' || gen_random_uuid()::text || '.pdf',
            p_file_checksum_sha256 := repeat('a', 64),
            p_file_size_bytes := 1024,
            p_mime_type := 'image/jpeg',
            p_metadata := '{}'::jsonb,
            p_ip_address := '127.0.0.1',
            p_request_id := 'req-mime'
        );
        RAISE EXCEPTION 'FAIL [5]: Invalid MIME type was permitted!';
    EXCEPTION
        WHEN check_violation THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [5]: Non-PDF mime_type rejected by RPC check';
    END;

    -- Invalid Category validation
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.create_medical_report_atomic(
            p_auth_user_id := v_patient_user_a,
            p_report_id := 'REP-2026-BAD002',
            p_title := 'Bad Category',
            p_category := 'invalid_cat',
            p_report_date := CURRENT_DATE,
            p_file_storage_path := 'reports/' || v_profile_a_id::text || '/' || gen_random_uuid()::text || '.pdf',
            p_file_checksum_sha256 := repeat('a', 64),
            p_file_size_bytes := 1024,
            p_mime_type := 'application/pdf',
            p_metadata := '{}'::jsonb,
            p_ip_address := '127.0.0.1',
            p_request_id := 'req-cat'
        );
        RAISE EXCEPTION 'FAIL [6]: Invalid category was permitted!';
    EXCEPTION
        WHEN check_violation THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [6]: Invalid category rejected by RPC check';
    END;

    -- Non-PDF storage path validation
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.create_medical_report_atomic(
            p_auth_user_id := v_patient_user_a,
            p_report_id := 'REP-2026-BAD003',
            p_title := 'Bad Extension',
            p_category := 'other',
            p_report_date := CURRENT_DATE,
            p_file_storage_path := 'reports/' || v_profile_a_id::text || '/test.png',
            p_file_checksum_sha256 := repeat('a', 64),
            p_file_size_bytes := 1024,
            p_mime_type := 'application/pdf',
            p_metadata := '{}'::jsonb,
            p_ip_address := '127.0.0.1',
            p_request_id := 'req-path'
        );
        RAISE EXCEPTION 'FAIL [7]: Non-PDF file_storage_path extension was permitted!';
    EXCEPTION
        WHEN check_violation THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [7]: Non-PDF file_storage_path extension rejected by RPC check';
    END;

    RAISE NOTICE '--- 5. Testing Atomic Report Creation RPC & Audit Emission ---';
    v_test_count := v_test_count + 1;
    v_report_res := public.create_medical_report_atomic(
        p_auth_user_id := v_patient_user_a,
        p_report_id := 'REP-2026-SQL001',
        p_title := 'Complete Blood Count Panel',
        p_category := 'blood_test',
        p_report_date := '2026-02-15'::DATE,
        p_file_storage_path := 'reports/' || v_profile_a_id::text || '/' || gen_random_uuid()::text || '.pdf',
        p_file_checksum_sha256 := repeat('f', 64),
        p_file_size_bytes := 20480,
        p_mime_type := 'application/pdf',
        p_metadata := '{"notes": "Fasting blood panel"}'::JSONB,
        p_ip_address := '127.0.0.1',
        p_request_id := 'req-sql-test-01'
    );

    v_report_uuid := (v_report_res->>'id')::UUID;
    IF v_report_uuid IS NOT NULL AND (v_report_res->>'patient_id')::UUID = v_profile_a_id THEN
        -- Check audit log
        SELECT COUNT(*) INTO v_audit_count
        FROM public.audit_logs
        WHERE entity_id = v_report_uuid::text
          AND action = 'medical_report_uploaded'
          AND actor_user_id = v_patient_user_a;

        IF v_audit_count = 1 THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [8]: create_medical_report_atomic created record and durable audit log';
        ELSE
            RAISE EXCEPTION 'FAIL [8]: Audit log record not created for report upload';
        END IF;
    ELSE
        RAISE EXCEPTION 'FAIL [8]: create_medical_report_atomic failed to return expected report data';
    END IF;

    RAISE NOTICE '--- 6. Testing Atomic Report Deletion RPC & Cross-Patient Protection ---';
    -- Cross-patient deletion attempt by Patient B on Patient A's report must fail
    v_test_count := v_test_count + 1;
    BEGIN
        v_delete_res := public.delete_medical_report_atomic(
            p_auth_user_id := v_patient_user_b,
            p_report_id := v_report_uuid,
            p_ip_address := '127.0.0.1',
            p_request_id := 'req-sql-unauth-del'
        );
        RAISE EXCEPTION 'FAIL [9]: Cross-patient report deletion was permitted!';
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLERRM LIKE '%no_data_found%' OR SQLERRM LIKE '%not found%' THEN
                v_pass_count := v_pass_count + 1;
                RAISE NOTICE 'PASS [9]: Unauthorized cross-patient deletion denied by RPC';
            ELSE
                RAISE EXCEPTION 'FAIL [9]: Unexpected error: %', SQLERRM;
            END IF;
    END;

    -- Authorized deletion by Patient A (owner) must succeed
    v_test_count := v_test_count + 1;
    v_delete_res := public.delete_medical_report_atomic(
        p_auth_user_id := v_patient_user_a,
        p_report_id := v_report_uuid,
        p_ip_address := '127.0.0.1',
        p_request_id := 'req-sql-auth-del'
    );

    IF (v_delete_res->>'success')::BOOLEAN = TRUE THEN
        -- Verify record removed from medical_reports
        IF NOT EXISTS (SELECT 1 FROM public.medical_reports WHERE id = v_report_uuid) THEN
            -- Verify deletion audit log
            SELECT COUNT(*) INTO v_audit_count
            FROM public.audit_logs
            WHERE entity_id = v_report_uuid::text
              AND action = 'medical_report_deleted'
              AND actor_user_id = v_patient_user_a;

            IF v_audit_count = 1 THEN
                v_pass_count := v_pass_count + 1;
                RAISE NOTICE 'PASS [10]: delete_medical_report_atomic deleted report and created durable audit log';
            ELSE
                RAISE EXCEPTION 'FAIL [10]: Deletion audit log missing';
            END IF;
        ELSE
            RAISE EXCEPTION 'FAIL [10]: Report record still exists in medical_reports after deletion';
        END IF;
    ELSE
        RAISE EXCEPTION 'FAIL [10]: delete_medical_report_atomic did not report success';
    END IF;

    RAISE NOTICE '=== All % tests passed successfully (%/%) ===', v_test_count, v_pass_count, v_test_count;
END $$;

-- ------------------------------------------------------------------------------
-- CLEANUP TEST FIXTURES
-- ------------------------------------------------------------------------------
ALTER TABLE public.audit_logs DISABLE TRIGGER trg_audit_logs_immutable;
DELETE FROM public.audit_logs WHERE actor_user_id IN (
    '88888888-8888-8888-8888-888888888881',
    '88888888-8888-8888-8888-888888888882'
);
ALTER TABLE public.audit_logs ENABLE TRIGGER trg_audit_logs_immutable;

DELETE FROM public.patient_profiles WHERE user_id IN (
    '88888888-8888-8888-8888-888888888881',
    '88888888-8888-8888-8888-888888888882'
);
DELETE FROM public.users WHERE id IN (
    '88888888-8888-8888-8888-888888888881',
    '88888888-8888-8888-8888-888888888882'
);
DELETE FROM auth.users WHERE id IN (
    '88888888-8888-8888-8888-888888888881',
    '88888888-8888-8888-8888-888888888882'
);

\echo '=== Secure Medical Reports Management Integration Test Suite Completed Successfully ==='
