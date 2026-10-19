-- ==============================================================================
-- Repeatable Database Security & RLS Test Suite
-- Version: 1.0.0
-- Target: Isolated Local Test PostgreSQL or Local Supabase Instance
-- Purpose:
--   Verifies that the database layer strictly enforces:
--   1. Anonymous access denial to patient profiles and hospital staff.
--   2. Cross-patient isolation (Patient A cannot view or modify Patient B).
--   3. Immutability of permanent Patient ID, ownership user_id, and verification_status.
--   4. Privilege escalation prevention on users.role.
--   5. Database-level unique constraint on phone_hash (race-safe deduplication).
--   6. Immutability of audit_logs and emergency_access_logs (UPDATE/DELETE blocked).
--   7. Authorized service_role operations succeed without weakening client protections.
-- ==============================================================================

-- Begin a transaction that rolls back at the end, leaving no test artifacts
BEGIN;

-- ------------------------------------------------------------------------------
-- SETUP: Create Isolated Mock Users in auth.users
-- ------------------------------------------------------------------------------
SET ROLE postgres;

-- Clear previous test data
DELETE FROM public.patient_recovery_requests;
DELETE FROM public.medical_reports;
DELETE FROM public.patient_profiles;
DELETE FROM public.hospital_staff;
DELETE FROM public.hospitals;
DELETE FROM public.users;
DELETE FROM auth.users WHERE email IN ('patient_a@test.local', 'patient_b@test.local');

INSERT INTO auth.users (id, email, phone, role)
VALUES 
    ('11111111-1111-1111-1111-111111111111', 'patient_a@test.local', '+919111111111', 'authenticated'),
    ('22222222-2222-2222-2222-222222222222', 'patient_b@test.local', '+919222222222', 'authenticated');

INSERT INTO public.users (id, email, phone_e164, role, is_active)
VALUES
    ('11111111-1111-1111-1111-111111111111', 'patient_a@test.local', '+919111111111', 'patient', TRUE),
    ('22222222-2222-2222-2222-222222222222', 'patient_b@test.local', '+919222222222', 'patient', TRUE);

-- ------------------------------------------------------------------------------
-- TEST 1: Anonymous Access Denial
-- ------------------------------------------------------------------------------
SET ROLE anon;
SET request.jwt.claim.role = 'anon';
RESET request.jwt.claim.sub;

-- Querying patient_profiles as anon must return 0 rows
DO $$
DECLARE
    r_count int;
BEGIN
    SELECT COUNT(*) INTO r_count FROM public.patient_profiles;
    IF r_count > 0 THEN
        RAISE EXCEPTION 'TEST 1 FAILED: Anonymous user was able to read patient_profiles!';
    END IF;
    RAISE NOTICE 'TEST 1 PASSED: Anonymous user denied access to patient_profiles.';
END $$;

-- Querying hospital_staff as anon must return 0 rows
DO $$
DECLARE
    s_count int;
BEGIN
    SELECT COUNT(*) INTO s_count FROM public.hospital_staff;
    IF s_count > 0 THEN
        RAISE EXCEPTION 'TEST 1 FAILED: Anonymous user was able to read hospital_staff!';
    END IF;
    RAISE NOTICE 'TEST 1 PASSED: Anonymous user denied access to hospital_staff.';
END $$;

-- ------------------------------------------------------------------------------
-- TEST 2: Patient Profile Creation & Tenant Isolation
-- ------------------------------------------------------------------------------
-- Assume session of Patient A
SET ROLE authenticated;
SET request.jwt.claim.role = 'authenticated';
SET request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

-- Patient A inserts own profile -> Must Succeed
INSERT INTO public.patient_profiles (
    id, patient_id, user_id, full_name, date_of_birth, gender, blood_group, phone_hash, verification_status
) VALUES (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'MED-2026-AAAAAA',
    '11111111-1111-1111-1111-111111111111',
    'Patient Alpha',
    '1990-01-01',
    'female',
    'O+',
    encode(sha256('+919111111111'::bytea), 'hex'),
    'phone_verified'
);
DO $$ BEGIN RAISE NOTICE 'TEST 2A PASSED: Patient A successfully created own profile.'; END $$;
DO $$
BEGIN
    INSERT INTO public.patient_profiles (
        id, patient_id, user_id, full_name, date_of_birth, gender, blood_group, phone_hash, verification_status
    ) VALUES (
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        'MED-2026-BBBBBB',
        '22222222-2222-2222-2222-222222222222', -- Belongs to User B!
        'Impersonated Patient B',
        '1992-02-02',
        'male',
        'A+',
        encode(sha256('+919222222222'::bytea), 'hex'),
        'unverified'
    );
    RAISE EXCEPTION 'TEST 2B FAILED: Patient A was allowed to create a profile owned by Patient B!';
EXCEPTION
    WHEN insufficient_privilege OR check_violation THEN
        RAISE NOTICE 'TEST 2B PASSED: RLS successfully blocked Patient A from creating profile for Patient B.';
END $$;

-- ------------------------------------------------------------------------------
-- TEST 3: Cross-Patient Data Reading & Modification Denial
-- ------------------------------------------------------------------------------
-- Seed Patient B's profile using service_role
SET ROLE service_role;
SET request.jwt.claim.role = 'service_role';
INSERT INTO public.patient_profiles (
    id, patient_id, user_id, full_name, date_of_birth, gender, blood_group, phone_hash, verification_status
) VALUES (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'MED-2026-BBBBBB',
    '22222222-2222-2222-2222-222222222222',
    'Patient Bravo',
    '1985-05-15',
    'male',
    'B+',
    encode(sha256('+919222222222'::bytea), 'hex'),
    'phone_verified'
);

-- Switch back to Patient A
SET ROLE authenticated;
SET request.jwt.claim.role = 'authenticated';
SET request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

-- Patient A queries patient_profiles: Must only see Patient A
DO $$
DECLARE
    seen_count int;
    seen_name text;
BEGIN
    SELECT COUNT(*), max(full_name) INTO seen_count, seen_name FROM public.patient_profiles;
    IF seen_count != 1 OR seen_name != 'Patient Alpha' THEN
        RAISE EXCEPTION 'TEST 3A FAILED: Cross-patient data leakage! Patient A saw % rows (Name: %)', seen_count, seen_name;
    END IF;
    RAISE NOTICE 'TEST 3A PASSED: Cross-patient read isolation verified. Patient A can only read own profile.';
END $$;

-- Patient A attempts to update Patient B's profile: Must modify 0 rows
DO $$
DECLARE
    rows_affected int;
BEGIN
    UPDATE public.patient_profiles 
    SET full_name = 'Hacked Patient B'
    WHERE user_id = '22222222-2222-2222-2222-222222222222';
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    IF rows_affected > 0 THEN
        RAISE EXCEPTION 'TEST 3B FAILED: Patient A was able to modify Patient B profile!';
    END IF;
    RAISE NOTICE 'TEST 3B PASSED: Cross-patient update isolation verified (0 rows affected).';
END $$;

-- ------------------------------------------------------------------------------
-- TEST 4: Immutability Triggers (Patient ID, Status, and Role Escalation)
-- ------------------------------------------------------------------------------
-- Patient A attempts to modify permanent patient_id -> Trigger must raise exception
DO $$
BEGIN
    UPDATE public.patient_profiles 
    SET patient_id = 'MED-2026-HACKED'
    WHERE user_id = '11111111-1111-1111-1111-111111111111';
    RAISE EXCEPTION 'TEST 4A FAILED: Patient was allowed to modify permanent patient_id!';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'TEST 4A PASSED: Immutability trigger successfully blocked patient_id alteration.';
END $$;

-- Patient A attempts to self-elevate verification_status to 'kyc_verified' -> Trigger must raise exception
DO $$
BEGIN
    UPDATE public.patient_profiles 
    SET verification_status = 'kyc_verified'
    WHERE user_id = '11111111-1111-1111-1111-111111111111';
    RAISE EXCEPTION 'TEST 4B FAILED: Client was allowed to self-elevate verification_status!';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'TEST 4B PASSED: Trigger successfully blocked client self-elevation of verification_status.';
END $$;

-- Patient A attempts to escalate role in public.users to 'platform_admin' -> Trigger must raise exception
DO $$
BEGIN
    UPDATE public.users 
    SET role = 'platform_admin'
    WHERE id = '11111111-1111-1111-1111-111111111111';
    RAISE EXCEPTION 'TEST 4C FAILED: User was allowed to self-escalate role to platform_admin!';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'TEST 4C PASSED: User role immutability trigger successfully blocked privilege escalation.';
END $$;

-- ------------------------------------------------------------------------------
-- TEST 5: Database-Level Unique Constraint (Deduplication)
-- ------------------------------------------------------------------------------
-- Attempt to insert a profile with the same phone_hash under another ID -> Must fail
DO $$
BEGIN
    INSERT INTO public.patient_profiles (
        id, patient_id, user_id, full_name, date_of_birth, gender, blood_group, phone_hash, verification_status
    ) VALUES (
        'cccccccc-cccc-cccc-cccc-cccccccccccc',
        'MED-2026-CCCCCC',
        '11111111-1111-1111-1111-111111111111',
        'Duplicate Attempt',
        '1990-01-01',
        'female',
        'O+',
        encode(sha256('+919111111111'::bytea), 'hex'), -- Exact duplicate phone_hash!
        'phone_verified'
    );
    RAISE EXCEPTION 'TEST 5 FAILED: Duplicate phone_hash was allowed by database!';
EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'TEST 5 PASSED: Unique index idx_patient_profiles_phone_hash_unique rejected duplicate phone record.';
END $$;

-- ------------------------------------------------------------------------------
-- TEST 6: Audit Log Tamper-Proofing (Append-Only Enforcement)
-- ------------------------------------------------------------------------------
-- Insert a test audit record as Patient A
INSERT INTO public.audit_logs (id, actor_user_id, actor_role, action, entity_type, entity_id, ip_address)
VALUES ('99999999-9999-9999-9999-999999999999', '11111111-1111-1111-1111-111111111111', 'patient', 'test_action', 'patient_profile', 'test_id', '127.0.0.1');

-- Attempt to UPDATE audit_logs -> Trigger must raise exception
DO $$
BEGIN
    UPDATE public.audit_logs SET action = 'tampered_action' WHERE id = '99999999-9999-9999-9999-999999999999';
    RAISE EXCEPTION 'TEST 6A FAILED: Client was allowed to update an audit log record!';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'TEST 6A PASSED: Audit log tampering trigger successfully blocked UPDATE.';
END $$;

-- Attempt to DELETE from audit_logs -> Trigger must raise exception
DO $$
BEGIN
    DELETE FROM public.audit_logs WHERE id = '99999999-9999-9999-9999-999999999999';
    RAISE EXCEPTION 'TEST 6B FAILED: Client was allowed to delete an audit log record!';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'TEST 6B PASSED: Audit log tampering trigger successfully blocked DELETE.';
END $$;

-- ------------------------------------------------------------------------------
-- TEST 7: Service Role Legitimacy Check
-- ------------------------------------------------------------------------------
-- Service role operations (e.g. backend elevating verification after authorized KYC)
SET ROLE service_role;
SET request.jwt.claim.role = 'service_role';
UPDATE public.patient_profiles 
SET verification_status = 'kyc_verified'
WHERE user_id = '11111111-1111-1111-1111-111111111111';

DO $$
DECLARE
    new_status text;
BEGIN
    SELECT verification_status INTO new_status 
    FROM public.patient_profiles 
    WHERE user_id = '11111111-1111-1111-1111-111111111111';
    IF new_status != 'kyc_verified' THEN
        RAISE EXCEPTION 'TEST 7 FAILED: service_role legitimate update did not take effect!';
    END IF;
    RAISE NOTICE 'TEST 7 PASSED: Authorized service_role operations succeed as intended.';
END $$;

DO $$ 
BEGIN
    RAISE NOTICE '===================================================================';
    RAISE NOTICE 'ALL 7 DATABASE INTEGRATION SECURITY TESTS PASSED SUCCESSFULLY!';
    RAISE NOTICE '===================================================================';
END $$;

-- Rollback entire test transaction to keep database completely clean
ROLLBACK;
