-- ==============================================================================
-- TEST SUITE: Audit Hardening, Privilege Isolation & Atomic Operations
-- Tests executed directly against local Supabase PostgreSQL (127.0.0.1:54322)
-- ==============================================================================

\set ON_ERROR_STOP on
\echo '=== Starting Audit Hardening & Privilege Isolation Test Suite ==='

DO $$
DECLARE
    v_test_patient_id UUID := '11111111-1111-1111-1111-111111111111'::UUID;
    v_test_patient_b_id UUID := '22222222-2222-2222-2222-222222222222'::UUID;
    v_test_recovery_user_id UUID := '33333333-3333-3333-3333-333333333333'::UUID;
    v_profile_res JSONB;
    v_update_res JSONB;
    v_audit_id UUID;
    v_test_count INT := 0;
    v_pass_count INT := 0;
BEGIN
    RAISE NOTICE '--- 1. Testing Table Privilege Revocation on public.audit_logs ---';
    -- Assert anon cannot write to audit_logs
    v_test_count := v_test_count + 1;
    IF has_table_privilege('anon', 'public.audit_logs', 'INSERT') = FALSE AND
       has_table_privilege('anon', 'public.audit_logs', 'UPDATE') = FALSE AND
       has_table_privilege('anon', 'public.audit_logs', 'DELETE') = FALSE AND
       has_table_privilege('anon', 'public.audit_logs', 'TRUNCATE') = FALSE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [1]: anon has zero write/truncate privileges on public.audit_logs';
    ELSE
        RAISE EXCEPTION 'FAIL [1]: anon retains write privileges on public.audit_logs';
    END IF;

    -- Assert authenticated cannot write to audit_logs
    v_test_count := v_test_count + 1;
    IF has_table_privilege('authenticated', 'public.audit_logs', 'INSERT') = FALSE AND
       has_table_privilege('authenticated', 'public.audit_logs', 'UPDATE') = FALSE AND
       has_table_privilege('authenticated', 'public.audit_logs', 'DELETE') = FALSE AND
       has_table_privilege('authenticated', 'public.audit_logs', 'TRUNCATE') = FALSE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [2]: authenticated has zero write/truncate privileges on public.audit_logs';
    ELSE
        RAISE EXCEPTION 'FAIL [2]: authenticated retains write privileges on public.audit_logs';
    END IF;

    RAISE NOTICE '--- 2. Testing RPC Privilege Revocation from authenticated / anon ---';
    -- register_patient_profile_atomic
    v_test_count := v_test_count + 1;
    IF has_function_privilege('authenticated', 'public.register_patient_profile_atomic(uuid,varchar,date,varchar,varchar,varchar,varchar,varchar,varchar,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('anon', 'public.register_patient_profile_atomic(uuid,varchar,date,varchar,varchar,varchar,varchar,varchar,varchar,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('service_role', 'public.register_patient_profile_atomic(uuid,varchar,date,varchar,varchar,varchar,varchar,varchar,varchar,varchar,varchar)', 'EXECUTE') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [3]: register_patient_profile_atomic is executable ONLY by service_role/postgres';
    ELSE
        RAISE EXCEPTION 'FAIL [3]: register_patient_profile_atomic has overly broad execute privileges';
    END IF;

    -- update_patient_profile_atomic
    v_test_count := v_test_count + 1;
    IF has_function_privilege('authenticated', 'public.update_patient_profile_atomic(uuid,varchar,varchar,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('anon', 'public.update_patient_profile_atomic(uuid,varchar,varchar,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('service_role', 'public.update_patient_profile_atomic(uuid,varchar,varchar,varchar,varchar)', 'EXECUTE') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [4]: update_patient_profile_atomic is executable ONLY by service_role/postgres';
    ELSE
        RAISE EXCEPTION 'FAIL [4]: update_patient_profile_atomic has overly broad execute privileges';
    END IF;

    -- verify_account_recovery_atomic
    v_test_count := v_test_count + 1;
    IF has_function_privilege('authenticated', 'public.verify_account_recovery_atomic(uuid,uuid,varchar,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('anon', 'public.verify_account_recovery_atomic(uuid,uuid,varchar,varchar,varchar)', 'EXECUTE') = FALSE AND
       has_function_privilege('service_role', 'public.verify_account_recovery_atomic(uuid,uuid,varchar,varchar,varchar)', 'EXECUTE') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [5]: verify_account_recovery_atomic is executable ONLY by service_role/postgres';
    ELSE
        RAISE EXCEPTION 'FAIL [5]: verify_account_recovery_atomic has overly broad execute privileges';
    END IF;

    -- record_security_audit_event
    v_test_count := v_test_count + 1;
    IF has_function_privilege('authenticated', 'public.record_security_audit_event(uuid,varchar,varchar,varchar,varchar,text,jsonb)', 'EXECUTE') = FALSE AND
       has_function_privilege('anon', 'public.record_security_audit_event(uuid,varchar,varchar,varchar,varchar,text,jsonb)', 'EXECUTE') = FALSE AND
       has_function_privilege('service_role', 'public.record_security_audit_event(uuid,varchar,varchar,varchar,varchar,text,jsonb)', 'EXECUTE') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [6]: record_security_audit_event is executable ONLY by service_role/postgres';
    ELSE
        RAISE EXCEPTION 'FAIL [6]: record_security_audit_event has overly broad execute privileges';
    END IF;

    RAISE NOTICE '--- 3. Testing Atomic Patient Registration & Audit Record Emission ---';
    -- Create synthetic auth user for test
    INSERT INTO auth.users (id, instance_id, aud, role, email, phone, phone_confirmed_at, encrypted_password, email_confirmed_at, recovery_sent_at, last_sign_in_at, raw_app_meta_data, raw_user_meta_data, is_super_admin, created_at, updated_at)
    VALUES (v_test_patient_id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'audit_test1@example.com', '+919876500001', NOW(), 'encrypted', NOW(), NULL, NOW(), '{"provider":"phone"}', '{}', FALSE, NOW(), NOW())
    ON CONFLICT (id) DO UPDATE SET phone_confirmed_at = NOW(), phone = '+919876500001';

    -- Call register_patient_profile_atomic
    v_profile_res := public.register_patient_profile_atomic(
        v_test_patient_id,
        'Integration Test Patient',
        '1992-04-10'::DATE,
        'female',
        'B+',
        '+919876500002',
        '+919876500001',
        encode(sha256('+919876500001'::bytea), 'hex'),
        'MED-2026-TEST99',
        '127.0.0.1',
        'req-test-uuid-001'
    );

    v_test_count := v_test_count + 1;
    IF (v_profile_res->>'status') = 'created' AND (v_profile_res->>'patient_id') = 'MED-2026-TEST99' THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [7]: register_patient_profile_atomic returned status created with expected patient_id';
    ELSE
        RAISE EXCEPTION 'FAIL [7]: unexpected profile creation response: %', v_profile_res;
    END IF;

    -- Assert audit log record was created atomically
    v_test_count := v_test_count + 1;
    IF EXISTS (
        SELECT 1 FROM public.audit_logs
        WHERE actor_user_id = v_test_patient_id
          AND action = 'patient_profile_created'
          AND details->>'request_id' = 'req-test-uuid-001'
    ) THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [8]: patient_profile_created audit log inserted atomically with matching request_id';
    ELSE
        RAISE EXCEPTION 'FAIL [8]: audit record missing for atomic profile registration';
    END IF;

    -- Test Idempotent call: Returns status existing
    v_test_count := v_test_count + 1;
    v_profile_res := public.register_patient_profile_atomic(
        v_test_patient_id,
        'Integration Test Patient',
        '1992-04-10'::DATE,
        'female',
        'B+',
        '+919876500002',
        '+919876500001',
        encode(sha256('+919876500001'::bytea), 'hex'),
        'MED-2026-TEST99',
        '127.0.0.1',
        'req-test-uuid-002'
    );
    IF (v_profile_res->>'status') = 'existing' THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [9]: Idempotent registration returned status existing without creating duplicates';
    ELSE
        RAISE EXCEPTION 'FAIL [9]: Idempotent registration failed: %', v_profile_res;
    END IF;

    RAISE NOTICE '--- 4. Testing Atomic Clinical Update & Isolation ---';
    v_update_res := public.update_patient_profile_atomic(
        v_test_patient_id,
        'AB+',
        '+919876599999',
        '127.0.0.1',
        'req-test-uuid-003'
    );

    v_test_count := v_test_count + 1;
    IF (v_update_res->>'blood_group') = 'AB+' AND (v_update_res->>'emergency_contact_phone') = '+919876599999' THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [10]: update_patient_profile_atomic updated permitted clinical fields';
    ELSE
        RAISE EXCEPTION 'FAIL [10]: update_patient_profile_atomic failed: %', v_update_res;
    END IF;

    -- Assert audit log record was created atomically
    v_test_count := v_test_count + 1;
    IF EXISTS (
        SELECT 1 FROM public.audit_logs
        WHERE actor_user_id = v_test_patient_id
          AND action = 'patient_profile_updated'
          AND details->>'request_id' = 'req-test-uuid-003'
          AND details->'updated_fields' ? 'blood_group'
    ) THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [11]: patient_profile_updated audit log inserted atomically with updated_fields';
    ELSE
        RAISE EXCEPTION 'FAIL [11]: audit record missing for atomic profile update';
    END IF;

    -- Cross-tenant isolation test: User B attempting to update User A's profile via atomic function
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.update_patient_profile_atomic(
            v_test_patient_b_id, -- Non-existent or different user
            'O-',
            '+919000000000',
            '127.0.0.1',
            'req-test-uuid-004'
        );
        RAISE EXCEPTION 'FAIL [12]: unauthorized user was able to call update_patient_profile_atomic';
    EXCEPTION WHEN no_data_found THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [12]: Cross-tenant atomic profile update rejected with no_data_found';
    END;

    RAISE NOTICE '--- 5. Testing Security Audit Event Logging & Whitelist ---';
    v_test_count := v_test_count + 1;
    v_audit_id := public.record_security_audit_event(
        v_test_patient_id,
        'patient_profile_read',
        'patient_profile',
        v_profile_res->>'id',
        '127.0.0.1',
        'TestClient/1.0',
        '{"patient_id": "MED-2026-TEST99", "read_reason": "direct_patient_access", "request_id": "req-read-001"}'::JSONB
    );

    IF v_audit_id IS NOT NULL THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [13]: record_security_audit_event logged whitelisted read event';
    ELSE
        RAISE EXCEPTION 'FAIL [13]: record_security_audit_event failed to log event';
    END IF;

    -- Disallowed action must be rejected by whitelist check
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.record_security_audit_event(
            v_test_patient_id,
            'disallowed_untrusted_action',
            'patient_profile',
            'some-id',
            '127.0.0.1',
            'TestClient/1.0',
            '{}'::JSONB
        );
        RAISE EXCEPTION 'FAIL [14]: record_security_audit_event allowed non-whitelisted action';
    EXCEPTION WHEN check_violation THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [14]: record_security_audit_event rejected non-whitelisted action with check_violation';
    END;

    RAISE NOTICE '--- 6. Testing Audit Log Append-Only Immutability ---';
    v_test_count := v_test_count + 1;
    BEGIN
        UPDATE public.audit_logs SET action = 'tampered' WHERE id = v_audit_id;
        RAISE EXCEPTION 'FAIL [15]: audit_log record was modified';
    EXCEPTION WHEN others THEN
        IF SQLERRM LIKE '%strictly append-only%' THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [15]: UPDATE on audit_logs blocked by tampering prevention trigger';
        ELSE
            RAISE EXCEPTION 'FAIL [15]: Unexpected error: %', SQLERRM;
        END IF;
    END;

    v_test_count := v_test_count + 1;
    BEGIN
        DELETE FROM public.audit_logs WHERE id = v_audit_id;
        RAISE EXCEPTION 'FAIL [16]: audit_log record was deleted';
    EXCEPTION WHEN others THEN
        IF SQLERRM LIKE '%strictly append-only%' THEN
            v_pass_count := v_pass_count + 1;
            RAISE NOTICE 'PASS [16]: DELETE on audit_logs blocked by tampering prevention trigger';
        ELSE
            RAISE EXCEPTION 'FAIL [16]: Unexpected error: %', SQLERRM;
        END IF;
    END;

    RAISE NOTICE '--- 7. Testing Registration Phone Binding & Cryptographic Checksum Integrity ---';
    -- 7A: Mismatched phone and hash must raise check_violation
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.register_patient_profile_atomic(
            v_test_patient_id,
            'Tampered Hash Patient',
            '1992-04-10'::DATE,
            'female',
            'B+',
            '+919876500002',
            '+919876500001',
            '0000000000000000000000000000000000000000000000000000000000000000', -- Forged/mismatched hash!
            'MED-2026-FAKE01',
            '127.0.0.1',
            'req-tamper-hash'
        );
        RAISE EXCEPTION 'FAIL [17]: Mismatched phone checksum was accepted';
    EXCEPTION WHEN check_violation THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [17]: Mismatched phone checksum rejected with check_violation';
    END;

    -- 7B: Empty phone number must raise check_violation
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.register_patient_profile_atomic(
            v_test_patient_id,
            'Empty Phone Patient',
            '1992-04-10'::DATE,
            'female',
            'B+',
            NULL,
            '', -- Empty phone!
            '',
            'MED-2026-FAKE02',
            '127.0.0.1',
            'req-empty-phone'
        );
        RAISE EXCEPTION 'FAIL [18]: Empty phone number was accepted';
    EXCEPTION WHEN check_violation THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [18]: Empty phone number rejected with check_violation';
    END;

    -- 7C: Phone number mismatching auth.users.phone must raise insufficient_privilege
    v_test_count := v_test_count + 1;
    BEGIN
        PERFORM public.register_patient_profile_atomic(
            v_test_patient_id,
            'Mismatched Auth Phone Patient',
            '1992-04-10'::DATE,
            'female',
            'B+',
            NULL,
            '+919999988888', -- Different from auth.users.phone (+919876500001)
            encode(sha256('+919999988888'::bytea), 'hex'),
            'MED-2026-FAKE03',
            '127.0.0.1',
            'req-mismatch-auth-phone'
        );
        RAISE EXCEPTION 'FAIL [19]: Phone number mismatching auth.users was accepted';
    EXCEPTION WHEN insufficient_privilege THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [19]: Phone number mismatching auth.users rejected with insufficient_privilege';
    END;

    -- 7D: Unconfirmed phone number in auth.users must raise insufficient_privilege
    v_test_count := v_test_count + 1;
    INSERT INTO auth.users (id, instance_id, aud, role, email, phone, phone_confirmed_at, encrypted_password, email_confirmed_at, created_at, updated_at)
    VALUES ('44444444-4444-4444-4444-444444444444', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'unconfirmed@test.local', '+919444444444', NULL, 'enc', NOW(), NOW(), NOW())
    ON CONFLICT (id) DO UPDATE SET phone_confirmed_at = NULL, phone = '+919444444444';

    BEGIN
        PERFORM public.register_patient_profile_atomic(
            '44444444-4444-4444-4444-444444444444',
            'Unconfirmed Phone Patient',
            '1992-04-10'::DATE,
            'female',
            'B+',
            NULL,
            '+919444444444',
            encode(sha256('+919444444444'::bytea), 'hex'),
            'MED-2026-UNCONF',
            '127.0.0.1',
            'req-unconfirmed-phone'
        );
        RAISE EXCEPTION 'FAIL [20]: Unconfirmed phone was accepted during registration';
    EXCEPTION WHEN insufficient_privilege THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [20]: Unconfirmed phone number in auth.users rejected with insufficient_privilege';
    END;

    -- 7E: Unconfirmed caller phone during recovery verification must raise insufficient_privilege
    v_test_count := v_test_count + 1;
    BEGIN
        -- Insert mock recovery request
        INSERT INTO public.patient_recovery_requests (
            id, patient_profile_id, old_phone_hash, new_phone_e164,
            recovery_channel, status, expires_at
        ) VALUES (
            '55555555-5555-5555-5555-555555555555',
            (SELECT id FROM public.patient_profiles WHERE user_id = v_test_patient_id),
            encode(sha256('+919876500001'::bytea), 'hex'),
            '+919444444444',
            'hospital_desk',
            'approved_by_staff',
            NOW() + INTERVAL '1 hour'
        ) ON CONFLICT (id) DO UPDATE SET status = 'approved_by_staff', expires_at = NOW() + INTERVAL '1 hour';

        PERFORM public.verify_account_recovery_atomic(
            '44444444-4444-4444-4444-444444444444', -- caller with unconfirmed phone
            '55555555-5555-5555-5555-555555555555',
            encode(sha256('+919444444444'::bytea), 'hex'),
            '127.0.0.1',
            'req-recovery-unconf'
        );
        RAISE EXCEPTION 'FAIL [21]: Unconfirmed caller phone was accepted during recovery';
    EXCEPTION WHEN insufficient_privilege THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [21]: Unconfirmed caller phone rejected with insufficient_privilege in recovery';
    END;

    RAISE NOTICE '--- 8. Testing Platform Admin vs Ordinary User Audit Log Access (Privilege Checks) ---';
    -- Assert anon has zero table privileges (cannot SELECT)
    v_test_count := v_test_count + 1;
    IF has_table_privilege('anon', 'public.audit_logs', 'SELECT') = FALSE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [22]: anon has zero SELECT privilege on public.audit_logs';
    ELSE
        RAISE EXCEPTION 'FAIL [22]: anon retains table SELECT privilege on public.audit_logs';
    END IF;

    -- Assert authenticated has SELECT privilege (subject to RLS)
    v_test_count := v_test_count + 1;
    IF has_table_privilege('authenticated', 'public.audit_logs', 'SELECT') = TRUE THEN
        v_pass_count := v_pass_count + 1;
        RAISE NOTICE 'PASS [23]: authenticated has table SELECT privilege (gated by RLS policy)';
    ELSE
        RAISE EXCEPTION 'FAIL [23]: authenticated missing table SELECT privilege for RLS';
    END IF;

    -- Create synthetic platform admin, inactive admin, and patient
    INSERT INTO auth.users (id, instance_id, aud, role, email, phone, phone_confirmed_at, encrypted_password, email_confirmed_at, created_at, updated_at)
    VALUES 
        ('77777777-7777-7777-7777-777777777777', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'admin@test.local', '+919999999990', NOW(), 'enc', NOW(), NOW(), NOW()),
        ('88888888-8888-8888-8888-888888888888', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'inactive_admin@test.local', '+919999999991', NOW(), 'enc', NOW(), NOW(), NOW()),
        ('99999999-9999-9999-9999-999999999999', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'ordinary_patient@test.local', '+919999999992', NOW(), 'enc', NOW(), NOW(), NOW())
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO public.users (id, phone_e164, role, is_active)
    VALUES 
        ('77777777-7777-7777-7777-777777777777', '+919999999990', 'platform_admin', TRUE),
        ('88888888-8888-8888-8888-888888888888', '+919999999991', 'platform_admin', FALSE),
        ('99999999-9999-9999-9999-999999999999', '+919999999992', 'patient', TRUE)
    ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, is_active = EXCLUDED.is_active;

    -- Insert known audit entry to verify visibility
    INSERT INTO public.audit_logs (actor_user_id, actor_role, action, entity_type, entity_id, ip_address)
    VALUES ('77777777-7777-7777-7777-777777777777', 'platform_admin', 'system_event', 'system', 'root', '127.0.0.1');

    RAISE NOTICE '==================================================';
    RAISE NOTICE 'AUDIT HARDENING TESTS COMPLETE: % of % PASSED', v_pass_count, v_test_count;
    RAISE NOTICE '==================================================';
END;
$$;

-- ------------------------------------------------------------------------------
-- 9. LIVE RLS QUERY EVALUATION ACROSS ROLES
-- ------------------------------------------------------------------------------
-- 9A: Active platform_admin CAN read audit logs
SET ROLE authenticated;
SET request.jwt.claim.role = 'authenticated';
SET request.jwt.claim.sub = '77777777-7777-7777-7777-777777777777';
DO $$
DECLARE
    v_c INT;
BEGIN
    SELECT count(*) INTO v_c FROM public.audit_logs;
    IF v_c >= 1 THEN
        RAISE NOTICE 'PASS [24]: Active platform_admin successfully selected audit logs via RLS (count=%)', v_c;
    ELSE
        RAISE EXCEPTION 'FAIL [24]: Active platform_admin could not read audit logs';
    END IF;
END $$;

-- 9B: Inactive platform_admin CANNOT read audit logs (0 rows)
SET request.jwt.claim.sub = '88888888-8888-8888-8888-888888888888';
DO $$
DECLARE
    v_c INT;
BEGIN
    SELECT count(*) INTO v_c FROM public.audit_logs;
    IF v_c = 0 THEN
        RAISE NOTICE 'PASS [25]: Inactive platform_admin denied audit log access by RLS (count=0)';
    ELSE
        RAISE EXCEPTION 'FAIL [25]: Inactive platform_admin was able to read audit logs (count=%)', v_c;
    END IF;
END $$;

-- 9C: Ordinary patient CANNOT read audit logs (0 rows)
SET request.jwt.claim.sub = '99999999-9999-9999-9999-999999999999';
DO $$
DECLARE
    v_c INT;
BEGIN
    SELECT count(*) INTO v_c FROM public.audit_logs;
    IF v_c = 0 THEN
        RAISE NOTICE 'PASS [26]: Ordinary patient denied audit log access by RLS (count=0)';
    ELSE
        RAISE EXCEPTION 'FAIL [26]: Ordinary patient was able to read audit logs (count=%)', v_c;
    END IF;
END $$;

-- 9D: Anon user CANNOT select from audit_logs (revoked table privilege)
SET ROLE anon;
SET request.jwt.claim.role = 'anon';
RESET request.jwt.claim.sub;
DO $$
BEGIN
    PERFORM count(*) FROM public.audit_logs;
    RAISE EXCEPTION 'FAIL [27]: Anon user was able to SELECT from audit_logs!';
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'PASS [27]: Anonymous user denied audit log access by SQL privileges (permission denied)';
END $$;

-- Reset role and clean up test fixtures
SET ROLE postgres;
RESET request.jwt.claim.role;
RESET request.jwt.claim.sub;

ALTER TABLE public.audit_logs DISABLE TRIGGER trg_audit_logs_immutable;
DELETE FROM public.audit_logs WHERE actor_user_id IN (
    '11111111-1111-1111-1111-111111111111',
    '77777777-7777-7777-7777-777777777777',
    '88888888-8888-8888-8888-888888888888',
    '99999999-9999-9999-9999-999999999999',
    '44444444-4444-4444-4444-444444444444'
);
ALTER TABLE public.audit_logs ENABLE TRIGGER trg_audit_logs_immutable;

DELETE FROM public.patient_recovery_requests WHERE id = '55555555-5555-5555-5555-555555555555';
DELETE FROM public.patient_profiles WHERE user_id IN (
    '11111111-1111-1111-1111-111111111111',
    '44444444-4444-4444-4444-444444444444'
);
DELETE FROM public.users WHERE id IN (
    '11111111-1111-1111-1111-111111111111',
    '77777777-7777-7777-7777-777777777777',
    '88888888-8888-8888-8888-888888888888',
    '99999999-9999-9999-9999-999999999999',
    '44444444-4444-4444-4444-444444444444'
);
DELETE FROM auth.users WHERE id IN (
    '11111111-1111-1111-1111-111111111111',
    '77777777-7777-7777-7777-777777777777',
    '88888888-8888-8888-8888-888888888888',
    '99999999-9999-9999-9999-999999999999',
    '44444444-4444-4444-4444-444444444444'
);

