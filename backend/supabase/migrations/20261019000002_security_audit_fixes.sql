-- ==============================================================================
-- Security Audit Fixes & Database-Level Enforcements (Phase 2B Validated)
-- Version: 20261019000002
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Safe pre-check and race-safe unique constraint on phone_hash.
--   2. Enable RLS on previously omitted tables (hospitals, hospital_staff).
--   3. Immutability trigger on patient_profiles (SECURITY INVOKER, auth.role() check).
--   4. Immutability trigger on users (SECURITY INVOKER, auth.role() privilege check).
--   5. Append-only enforcement on audit_logs and emergency_access_logs.
--   6. Hardened RLS policies for audit_logs and patient_recovery_requests.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. RACE-SAFE DEDUPLICATION WITH SAFE PRE-CHECK
-- ------------------------------------------------------------------------------
-- Guard against existing duplicates before creating the unique index
DO $$
BEGIN
    IF EXISTS (
        SELECT phone_hash 
        FROM public.patient_profiles 
        GROUP BY phone_hash 
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Cannot create unique index: duplicate phone_hash records exist in patient_profiles. Resolve duplicates before applying this migration.';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_profiles_phone_hash_unique 
    ON public.patient_profiles(phone_hash);

-- ------------------------------------------------------------------------------
-- 2. ENABLE ROW-LEVEL SECURITY ON HOSPITALS AND HOSPITAL STAFF
-- ------------------------------------------------------------------------------
-- Previously omitted in initial schema; must be protected from anonymous harvesting
ALTER TABLE public.hospitals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hospital_staff ENABLE ROW LEVEL SECURITY;

-- Hospitals: Verified active hospitals are viewable by authenticated users
DROP POLICY IF EXISTS "Anyone view verified hospitals" ON public.hospitals;
CREATE POLICY "Anyone view verified hospitals"
    ON public.hospitals FOR SELECT
    USING (verification_status = 'verified' AND is_active = TRUE);

-- Hospital Staff: Only active staff can view their own membership or colleagues in same hospital
DROP POLICY IF EXISTS "Staff view own hospital membership" ON public.hospital_staff;
CREATE POLICY "Staff view own hospital membership"
    ON public.hospital_staff FOR SELECT
    USING (
        user_id = auth.uid() OR
        hospital_id IN (
            SELECT hospital_id FROM public.hospital_staff 
            WHERE user_id = auth.uid() AND is_active = TRUE
        )
    );

-- ------------------------------------------------------------------------------
-- 3. PATIENT PROFILE IMMUTABILITY TRIGGER (SECURITY INVOKER)
-- ------------------------------------------------------------------------------
-- Prevents authenticated clients from modifying permanent patient_id, user_id,
-- or elevating verification_status.
-- Note: Uses SECURITY INVOKER (default) and checks auth.role() derived by Supabase
-- from the cryptographically verified JWT, preventing SECURITY DEFINER bypass.
CREATE OR REPLACE FUNCTION public.check_patient_profile_immutability()
RETURNS TRIGGER AS $$
DECLARE
    caller_role text := auth.role();
BEGIN
    -- Prevent altering permanent patient_id
    IF OLD.patient_id IS DISTINCT FROM NEW.patient_id THEN
        RAISE EXCEPTION 'Modification of permanent patient_id is strictly prohibited.';
    END IF;

    -- Prevent altering owner user_id mapping directly
    IF OLD.user_id IS DISTINCT FROM NEW.user_id THEN
        RAISE EXCEPTION 'Direct re-assignment of patient profile user_id is prohibited. Use authorized recovery workflows.';
    END IF;

    -- Prevent clients from self-elevating verification_status
    IF OLD.verification_status IS DISTINCT FROM NEW.verification_status THEN
        -- Only service_role or database superuser can elevate verification_status
        IF caller_role = 'authenticated' OR caller_role = 'anon' OR 
           (caller_role IS NULL AND session_user NOT IN ('service_role', 'postgres', 'supabase_admin')) THEN
            RAISE EXCEPTION 'Unauthorized attempt to modify patient verification status.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_patient_profile_immutability ON public.patient_profiles;
CREATE TRIGGER trg_patient_profile_immutability
    BEFORE UPDATE ON public.patient_profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.check_patient_profile_immutability();

-- ------------------------------------------------------------------------------
-- 4. USER ROLE IMMUTABILITY TRIGGER (PRIVILEGE ESCALATION PREVENTION)
-- ------------------------------------------------------------------------------
-- Prevents ordinary users from escalating their own role in public.users
CREATE OR REPLACE FUNCTION public.check_user_role_immutability()
RETURNS TRIGGER AS $$
DECLARE
    caller_role text := auth.role();
BEGIN
    IF OLD.role IS DISTINCT FROM NEW.role THEN
        IF caller_role = 'authenticated' OR caller_role = 'anon' OR 
           (caller_role IS NULL AND session_user NOT IN ('service_role', 'postgres', 'supabase_admin')) THEN
            RAISE EXCEPTION 'Privilege escalation attempt: Users cannot alter their own role.';
        END IF;
    END IF;

    IF OLD.id IS DISTINCT FROM NEW.id THEN
        RAISE EXCEPTION 'Modification of user primary identity id is prohibited.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_role_immutability ON public.users;
CREATE TRIGGER trg_user_role_immutability
    BEFORE UPDATE ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION public.check_user_role_immutability();

-- ------------------------------------------------------------------------------
-- 5. IMMUTABLE AUDIT LOGS TRIGGER
-- ------------------------------------------------------------------------------
-- Ensures audit_logs and emergency_access_logs are strictly append-only.
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
-- 6. STRENGTHENED ROW-LEVEL SECURITY POLICIES
-- ------------------------------------------------------------------------------

-- Ensure audit log insertions strictly record the authenticated user as actor
DROP POLICY IF EXISTS "Authenticated users insert audit logs" ON public.audit_logs;
CREATE POLICY "Authenticated users insert audit logs"
    ON public.audit_logs FOR INSERT
    WITH CHECK (auth.uid() IS NOT NULL AND (actor_user_id IS NULL OR actor_user_id = auth.uid()));

-- Protect patient_recovery_requests:
-- Drop direct client INSERT. Recovery requests must be initiated via the secure backend
-- service to enforce rate limiting, verification challenges, and audit logging.
DROP POLICY IF EXISTS "Patients insert own recovery requests" ON public.patient_recovery_requests;

-- Patients can only view their own recovery requests
DROP POLICY IF EXISTS "Patients view own recovery requests" ON public.patient_recovery_requests;
CREATE POLICY "Patients view own recovery requests"
    ON public.patient_recovery_requests FOR SELECT
    USING (
        patient_profile_id IN (
            SELECT id FROM public.patient_profiles WHERE user_id = auth.uid()
        )
    );
