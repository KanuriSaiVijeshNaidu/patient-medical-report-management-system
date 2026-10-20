-- ==============================================================================
-- TEST SUITE: Secure QR-Based Medical Report Sharing Integration Tests
-- Tests executed directly against local Supabase PostgreSQL (127.0.0.1:54322)
-- ==============================================================================

\set ON_ERROR_STOP on
\echo '=== Starting Secure QR Report Sharing Integration Test Suite ==='

DO $$
DECLARE
    v_patient_user_a UUID := '66666666-6666-6666-6666-666666666661'::UUID;
    v_patient_user_b UUID := '66666666-6666-6666-6666-666666666662'::UUID;
    v_profile_a_id UUID;
    v_profile_b_id UUID;
    v_report_a_id UUID;
    v_report_b_id UUID;
    v_grant_res JSONB;
    v_grant_id UUID;
    v_access_res JSONB;
    v_revoke_res JSONB;
    v_token_hash_a VARCHAR(64) := repeat('1', 64);
    v_token_hash_b VARCHAR(64) := repeat('2', 64);
    v_audit_count INT;
    v_test_count INT := 0;
    v_pass_count INT := 0;
BEGIN
    RAISE NOTICE '--- 1. Testing Function Privileges on Sharing RPCs ---';
    -- create_report_access_grant_atomic
    v_test_count := v_test_count + 1;
    IF has_function_privilege('authenticated', 'public.create_report_access_grant_atomic(uuid,uuid,varchar,integer,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('anon', 'public.create_report_access_grant_atomic(uuid,uuid,varchar,integer,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('service_role', 'public.create_report_access_grant_atomic(uuid,uuid,varchar,integer,varchar,varchar)', 'EXECUTE') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [1]: create_report_access_grant_atomic is executable ONLY by service_role/postgres';
    ELSE
        RAISE EXCEPTION 'FAIL [1]: create_report_access_grant_atomic has overly broad execute privileges';
    END IF;

    -- revoke_report_access_grant_atomic
    v_test_count := v_test_count + 1;
    IF has_function_privilege('authenticated', 'public.revoke_report_access_grant_atomic(uuid,uuid,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('anon', 'public.revoke_report_access_grant_atomic(uuid,uuid,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('service_role', 'public.revoke_report_access_grant_atomic(uuid,uuid,varchar,varchar)', 'EXECUTE') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [2]: revoke_report_access_grant_atomic is executable ONLY by service_role/postgres';
    ELSE
        RAISE EXCEPTION 'FAIL [2]: revoke_report_access_grant_atomic has overly broad execute privileges';
    END IF;

    -- validate_and_access_shared_report_atomic
    v_test_count := v_test_count + 1;
    IF has_function_privilege('authenticated', 'public.validate_and_access_shared_report_atomic(varchar,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('anon', 'public.validate_and_access_shared_report_atomic(varchar,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('service_role', 'public.validate_and_access_shared_report_atomic(varchar,varchar,varchar)', 'EXECUTE') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [3]: validate_and_access_shared_report_atomic is executable ONLY by service_role/postgres';
    ELSE
        RAISE EXCEPTION 'FAIL [3]: validate_and_access_shared_report_atomic has overly broad execute privileges';
    END IF;

    RAISE NOTICE '--- 2. Testing Table Write Privilege Revocation on public.record_access_grants ---';
    v_test_count := v_test_count + 1;
    IF has_table_privilege('anon', 'public.record_access_grants', 'INSERT') = FALSE AND
       has_table_privilege('anon', 'public.record_access_grants', 'UPDATE') = FALSE AND
       has_table_privilege('anon', 'public.record_access_grants', 'DELETE') = FALSE AND
       has_table_privilege('authenticated', 'public.record_access_grants', 'INSERT') = FALSE AND
       has_table_privilege('authenticated', 'public.record_access_grants', 'UPDATE') = FALSE AND
       has_table_privilege('authenticated', 'public.record_access_grants', 'DELETE') = FALSE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [4]: Direct client writes to public.record_access_grants are strictly revoked';
    ELSE
        RAISE EXCEPTION 'FAIL [4]: Clients retain direct write privileges on record_access_grants';
    END IF;

    RAISE NOTICE '--- 3. Setting Up Test Patients and Medical Reports ---';
    -- Clean previous artifacts if any
    DELETE FROM public.record_access_grants WHERE grant_token_hash IN (v_token_hash_a, v_token_hash_b);
    DELETE FROM public.medical_reports WHERE report_id LIKE 'REP-SHARE-%';
    DELETE FROM public.patient_profiles WHERE user_id IN (v_patient_user_a, v_patient_user_b);
    DELETE FROM public.users WHERE id IN (v_patient_user_a, v_patient_user_b);
    DELETE FROM auth.users WHERE id IN (v_patient_user_a, v_patient_user_b);

    INSERT INTO auth.users (id, instance_id, aud, role, email, phone, phone_confirmed_at, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, is_super_admin, created_at, updated_at)
    VALUES
        (v_patient_user_a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'share_a@example.com', '+919876543301', NOW(), 'enc', NOW(), '{"provider":"phone"}', '{}', FALSE, NOW(), NOW()),
        (v_patient_user_b, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'share_b@example.com', '+919876543302', NOW(), 'enc', NOW(), '{"provider":"phone"}', '{}', FALSE, NOW(), NOW());

    SELECT (public.register_patient_profile_atomic(
        v_patient_user_a, 'Patient Share A', '1991-03-15'::DATE, 'male', 'B+',
        '+919876543301', '+919876543301', encode(sha256('+919876543301'::bytea), 'hex'),
        'MED-2026-SHARA1', '127.0.0.1', 'req-setup-share-a'
    )->>'id')::UUID INTO v_profile_a_id;

    SELECT (public.register_patient_profile_atomic(
        v_patient_user_b, 'Patient Share B', '1993-05-20'::DATE, 'female', 'O+',
        '+919876543302', '+919876543302', encode(sha256('+919876543302'::bytea), 'hex'),
        'MED-2026-SHARB2', '127.0.0.1', 'req-setup-share-b'
    )->>'id')::UUID INTO v_profile_b_id;

    -- Create report for Patient A
    SELECT (public.create_medical_report_atomic(
        v_patient_user_a, 'REP-SHARE-001', 'Patient A Blood Panel', 'blood_test',
        '2026-02-10'::DATE, 'reports/' || v_profile_a_id::text || '/' || gen_random_uuid()::text || '.pdf',
        repeat('a', 64), 2048, 'application/pdf', '{}'::JSONB, '127.0.0.1', 'req-rep-a'
    )->>'id')::UUID INTO v_report_a_id;

    -- Create report for Patient B
    SELECT (public.create_medical_report_atomic(
        v_patient_user_b, 'REP-SHARE-002', 'Patient B Cardiology MRI', 'mri',
        '2026-02-12'::DATE, 'reports/' || v_profile_b_id::text || '/' || gen_random_uuid()::text || '.pdf',
        repeat('b', 64), 4096, 'application/pdf', '{}'::JSONB, '127.0.0.1', 'req-rep-b'
    )->>'id')::UUID INTO v_report_b_id;

    RAISE NOTICE '--- 4. Testing Atomic Share Creation & Cross-Patient Protection ---';
    -- Cross-patient share attempt: Patient A attempts to share Patient B's report
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.create_report_access_grant_atomic(
            v_patient_user_a, v_report_b_id, v_token_hash_a, 900, '127.0.0.1', 'req-cross-share'
        );
        RAISE EXCEPTION 'FAIL [5]: Patient A was able to share Patient B report!';
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLERRM LIKE '%access denied%' OR SQLERRM LIKE '%not found%' THEN
                v_pass_count := v_pass_count + 1;
                RAISE NOTICE 'PASS [5]: Unauthorized cross-patient share rejected by RPC';
            ELSE
                RAISE EXCEPTION 'FAIL [5]: Unexpected error: %', SQLERRM;
            END IF;
    END;

    -- Invalid duration check (<60 seconds)
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.create_report_access_grant_atomic(
            v_patient_user_a, v_report_a_id, v_token_hash_a, 30, '127.0.0.1', 'req-dur'
        );
        RAISE EXCEPTION 'FAIL [6]: Invalid short duration was permitted!';
    EXCEPTION
        WHEN check_violation THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [6]: Invalid expiry seconds (<60s) rejected by check';
    END;

    -- Valid share creation by Patient A for Report A
    v_test_count := v_test_count + 1;
    v_grant_res := public.create_report_access_grant_atomic(
        p_auth_user_id := v_patient_user_a,
        p_report_id := v_report_a_id,
        p_token_hash := v_token_hash_a,
        p_expires_in_seconds := 900,
        p_ip_address := '127.0.0.1',
        p_request_id := 'req-create-share-a'
    );
    v_grant_id := (v_grant_res->>'grant_id')::UUID;

    IF v_grant_id IS NOT NULL AND (v_grant_res->>'report_id') = 'REP-SHARE-001' THEN
        SELECT COUNT(*) INTO v_audit_count
        FROM public.audit_logs
        WHERE entity_id = v_grant_id::text
          AND action = 'report_share_created'
          AND actor_user_id = v_patient_user_a;

        IF v_audit_count = 1 THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [7]: create_report_access_grant_atomic created grant and durable audit event';
        ELSE
            RAISE EXCEPTION 'FAIL [7]: Audit event not created for share grant';
        END IF;
    ELSE
        RAISE EXCEPTION 'FAIL [7]: create_report_access_grant_atomic failed: %', v_grant_res;
    END IF;

    RAISE NOTICE '--- 5. Testing Recipient Token Validation & Access Increment ---';
    v_test_count := v_test_count + 1;
    v_access_res := public.validate_and_access_shared_report_atomic(
        p_token_hash := v_token_hash_a,
        p_ip_address := '127.0.0.1',
        p_request_id := 'req-recipient-view-1'
    );

    IF (v_access_res->>'report_id') = 'REP-SHARE-001' AND (v_access_res->>'access_count')::INT = 1 THEN
        -- Check audit event
        SELECT COUNT(*) INTO v_audit_count
        FROM public.audit_logs
        WHERE entity_id = v_report_a_id::text
          AND action = 'report_share_accessed';

        IF v_audit_count = 1 THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [8]: validate_and_access_shared_report_atomic incremented access count and emitted audit event';
        ELSE
            RAISE EXCEPTION 'FAIL [8]: Audit event missing for report access';
        END IF;
    ELSE
        RAISE EXCEPTION 'FAIL [8]: validate_and_access_shared_report_atomic returned unexpected data: %', v_access_res;
    END IF;

    RAISE NOTICE '--- 6. Testing Share Revocation Lifecycle ---';
    -- Cross-patient revocation: Patient B cannot revoke Patient A's grant
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.revoke_report_access_grant_atomic(
            v_patient_user_b, v_grant_id, '127.0.0.1', 'req-unauth-revoke'
        );
        RAISE EXCEPTION 'FAIL [9]: Patient B was able to revoke Patient A grant!';
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLERRM LIKE '%not found%' OR SQLERRM LIKE '%access denied%' THEN
                v_pass_count := v_pass_count + 1;
                RAISE NOTICE 'PASS [9]: Unauthorized revocation denied by RPC';
            ELSE
                RAISE EXCEPTION 'FAIL [9]: Unexpected error: %', SQLERRM;
            END IF;
    END;

    -- Authorized revocation by Patient A
    v_test_count := v_test_count + 1;
    v_revoke_res := public.revoke_report_access_grant_atomic(
        p_auth_user_id := v_patient_user_a,
        p_grant_id := v_grant_id,
        p_ip_address := '127.0.0.1',
        p_request_id := 'req-auth-revoke'
    );

    IF (v_revoke_res->>'success')::BOOLEAN = TRUE THEN
        SELECT COUNT(*) INTO v_audit_count
        FROM public.audit_logs
        WHERE entity_id = v_grant_id::text
          AND action = 'report_share_revoked'
          AND actor_user_id = v_patient_user_a;

        IF v_audit_count = 1 THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [10]: revoke_report_access_grant_atomic revoked grant and emitted durable audit log';
        ELSE
            RAISE EXCEPTION 'FAIL [10]: Revocation audit event missing';
        END IF;
    ELSE
        RAISE EXCEPTION 'FAIL [10]: Revocation failed: %', v_revoke_res;
    END IF;

    -- Attempting to access report with revoked token must now fail
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.validate_and_access_shared_report_atomic(
            p_token_hash := v_token_hash_a,
            p_ip_address := '127.0.0.1',
            p_request_id := 'req-view-after-revoke'
        );
        RAISE EXCEPTION 'FAIL [11]: Revoked token was still accepted!';
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLERRM LIKE '%revoked%' THEN
                v_pass_count := v_pass_count + 1;
                RAISE NOTICE 'PASS [11]: Subsequent recipient access denied on revoked grant';
            ELSE
                RAISE EXCEPTION 'FAIL [11]: Unexpected error on revoked token: %', SQLERRM;
            END IF;
    END;

    RAISE NOTICE '=== All % tests passed successfully (%/%) ===', v_test_count, v_pass_count, v_test_count;
END $$;

-- ------------------------------------------------------------------------------
-- CLEANUP TEST FIXTURES
-- ------------------------------------------------------------------------------
ALTER TABLE public.audit_logs DISABLE TRIGGER trg_audit_logs_immutable;
DELETE FROM public.audit_logs WHERE actor_user_id IN (
    '66666666-6666-6666-6666-666666666661',
    '66666666-6666-6666-6666-666666666662'
) OR entity_id IN (
    SELECT id::text FROM public.record_access_grants WHERE patient_id IN (
        SELECT id FROM public.patient_profiles WHERE user_id IN (
            '66666666-6666-6666-6666-666666666661',
            '66666666-6666-6666-6666-666666666662'
        )
    )
);
ALTER TABLE public.audit_logs ENABLE TRIGGER trg_audit_logs_immutable;

DELETE FROM public.record_access_grants WHERE patient_id IN (
    SELECT id FROM public.patient_profiles WHERE user_id IN (
        '66666666-6666-6666-6666-666666666661',
        '66666666-6666-6666-6666-666666666662'
    )
);
DELETE FROM public.medical_reports WHERE report_id LIKE 'REP-SHARE-%';
DELETE FROM public.patient_profiles WHERE user_id IN (
    '66666666-6666-6666-6666-666666666661',
    '66666666-6666-6666-6666-666666666662'
);
DELETE FROM public.users WHERE id IN (
    '66666666-6666-6666-6666-666666666661',
    '66666666-6666-6666-6666-666666666662'
);
DELETE FROM auth.users WHERE id IN (
    '66666666-6666-6666-6666-666666666661',
    '66666666-6666-6666-6666-666666666662'
);

\echo '=== Secure QR Report Sharing Integration Test Suite Completed Successfully ==='
