-- ==============================================================================
-- Security Audit Fixes & Database-Level Enforcements
-- Version: 20261019000002
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Race-safe unique constraint on phone_hash (database-level deduplication).
--   2. Immutability triggers on patient_profiles (patient_id, user_id, verification_status).
--   3. Immutability trigger on users (role privilege escalation prevention).
--   4. Immutable audit trail enforcement (disallow UPDATE and DELETE on audit logs).
--   5. Strengthened RLS policies for patient recovery and audit trails.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. RACE-SAFE DATABASE-LEVEL DEDUPLICATION
-- ------------------------------------------------------------------------------
-- Ensure that concurrent profile creation attempts cannot produce duplicate phone records.
CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_profiles_phone_hash_unique 
    ON public.patient_profiles(phone_hash);

-- ------------------------------------------------------------------------------
-- 2. PATIENT PROFILE IMMUTABILITY TRIGGER
-- ------------------------------------------------------------------------------
-- Prevents authenticated clients from modifying their permanent patient_id,
-- user_id mapping, or verification_status directly via client updates.
CREATE OR REPLACE FUNCTION public.check_patient_profile_immutability()
RETURNS TRIGGER AS $$
BEGIN
    -- Prevent altering permanent patient_id
    IF OLD.patient_id IS DISTINCT FROM NEW.patient_id THEN
        RAISE EXCEPTION 'Modification of permanent patient_id is strictly prohibited.';
    END IF;

    -- Prevent altering owner user_id mapping directly
    IF OLD.user_id IS DISTINCT FROM NEW.user_id THEN
        RAISE EXCEPTION 'Direct re-assignment of patient profile user_id is prohibited. Use authorized recovery workflows.';
    END IF;

    -- Prevent self-elevating verification_status
    IF OLD.verification_status IS DISTINCT FROM NEW.verification_status THEN
        -- Only service_role can elevate verification_status
        IF current_user NOT IN ('service_role', 'postgres', 'supabase_admin') THEN
            RAISE EXCEPTION 'Unauthorized attempt to modify patient verification status.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_patient_profile_immutability ON public.patient_profiles;
CREATE TRIGGER trg_patient_profile_immutability
    BEFORE UPDATE ON public.patient_profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.check_patient_profile_immutability();

-- ------------------------------------------------------------------------------
-- 3. USER ROLE IMMUTABILITY TRIGGER (PREVENT PRIVILEGE ESCALATION)
-- ------------------------------------------------------------------------------
-- Prevents users from updating their own role (e.g. from 'patient' to 'platform_admin').
CREATE OR REPLACE FUNCTION public.check_user_role_immutability()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.role IS DISTINCT FROM NEW.role THEN
        IF current_user NOT IN ('service_role', 'postgres', 'supabase_admin') THEN
            RAISE EXCEPTION 'Privilege escalation attempt: Users cannot alter their own role.';
        END IF;
    END IF;

    IF OLD.id IS DISTINCT FROM NEW.id THEN
        RAISE EXCEPTION 'Modification of user primary identity id is prohibited.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_user_role_immutability ON public.users;
CREATE TRIGGER trg_user_role_immutability
    BEFORE UPDATE ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION public.check_user_role_immutability();

-- ------------------------------------------------------------------------------
-- 4. IMMUTABLE AUDIT LOGS TRIGGER
-- ------------------------------------------------------------------------------
-- Ensures audit_logs and emergency_access_logs are strictly append-only.
-- Even if an update/delete policy is mistakenly granted, the trigger rejects it.
CREATE OR REPLACE FUNCTION public.prevent_audit_log_tampering()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit records are strictly append-only and cannot be updated or deleted.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON public.audit_logs;
CREATE TRIGGER trg_audit_logs_immutable
    BEFORE UPDATE OR DELETE ON public.audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION public.prevent_audit_log_tampering();

DROP TRIGGER IF EXISTS trg_emergency_logs_immutable ON public.emergency_access_logs;
CREATE TRIGGER trg_emergency_logs_immutable
    BEFORE UPDATE OR DELETE ON public.emergency_access_logs
    FOR EACH ROW
    EXECUTE FUNCTION public.prevent_audit_log_tampering();

-- ------------------------------------------------------------------------------
-- 5. STRENGTHENED ROW-LEVEL SECURITY POLICIES
-- ------------------------------------------------------------------------------

-- Ensure audit log insertions strictly record the authenticated user as the actor
DROP POLICY IF EXISTS "Authenticated users insert audit logs" ON public.audit_logs;
CREATE POLICY "Authenticated users insert audit logs"
    ON public.audit_logs FOR INSERT
    WITH CHECK (auth.uid() IS NOT NULL AND (actor_user_id IS NULL OR actor_user_id = auth.uid()));

-- Protect patient_recovery_requests:
-- Drop direct client INSERT. Recovery requests must be initiated via the secure backend
-- service to enforce rate limiting, verification challenges, and audit logging.
DROP POLICY IF EXISTS "Patients insert own recovery requests" ON public.patient_recovery_requests;
