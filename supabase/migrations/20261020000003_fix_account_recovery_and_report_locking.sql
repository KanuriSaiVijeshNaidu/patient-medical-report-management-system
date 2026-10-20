-- ==============================================================================
-- Forward-Only Fix: Account Recovery Immutability Authorization & Report Lock Isolation
-- Version: 20261020000003
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Authorizes user_id re-assignment in check_patient_profile_immutability
--      strictly when executing within the authorized atomic account recovery workflow
--      via transaction-local setting (app.in_account_recovery = 'true') and untrusted caller rejection.
--   2. Updates verify_account_recovery_atomic to set transaction-local recovery flag
--      during atomic re-linking.
--   3. Refines delete_medical_report_atomic row-lock to 'FOR UPDATE OF mr' to prevent
--      unnecessary coarse-grained exclusive locks on patient_profiles.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. AUTHORIZED PATIENT PROFILE IMMUTABILITY TRIGGER FUNCTION
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.check_patient_profile_immutability()
RETURNS TRIGGER AS $$
DECLARE
    caller_role text := auth.role();
    in_recovery text := current_setting('app.in_account_recovery', true);
BEGIN
    -- Prevent altering permanent patient_id
    IF OLD.patient_id IS DISTINCT FROM NEW.patient_id THEN
        RAISE EXCEPTION 'Modification of permanent patient_id is strictly prohibited.';
    END IF;

    -- Prevent altering owner user_id mapping directly unless in authorized atomic recovery workflow
    IF OLD.user_id IS DISTINCT FROM NEW.user_id THEN
        IF in_recovery IS DISTINCT FROM 'true' OR caller_role IN ('authenticated', 'anon') THEN
            RAISE EXCEPTION 'Direct re-assignment of patient profile user_id is prohibited. Use authorized recovery workflows.';
        END IF;
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


-- ------------------------------------------------------------------------------
-- 2. ATOMIC ACCOUNT RECOVERY WITH TRANSACTION-LOCAL AUTHORIZATION
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.verify_account_recovery_atomic(
    p_auth_user_id UUID,
    p_recovery_request_id UUID,
    p_new_phone_hash VARCHAR(64),
    p_ip_address VARCHAR(45),
    p_request_id VARCHAR(64)
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_req RECORD;
    v_profile RECORD;
    v_new_user RECORD;
    v_actor_role VARCHAR(50);
    v_auth_phone TEXT;
    v_phone_confirmed_at TIMESTAMPTZ;
    v_derived_phone_hash VARCHAR(64);
BEGIN
    -- 1. Fetch recovery request WITH ROW LOCK to prevent concurrent completion replays
    SELECT * INTO v_req FROM public.patient_recovery_requests 
    WHERE id = p_recovery_request_id FOR UPDATE;
    
    IF v_req.id IS NULL THEN
        RAISE EXCEPTION 'Recovery request % not found.', p_recovery_request_id
            USING ERRCODE = 'no_data_found';
    END IF;

    -- 2. State & Replay Check
    IF v_req.status != 'approved_by_staff' THEN
        RAISE EXCEPTION 'Recovery request has not been approved by hospital desk verification or has already been completed.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 3. Expiration Check
    IF v_req.expires_at <= NOW() THEN
        RAISE EXCEPTION 'Recovery request has expired.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 4. Verified New Account in auth.users & phone confirmation
    SELECT phone, phone_confirmed_at INTO v_auth_phone, v_phone_confirmed_at 
    FROM auth.users WHERE id = p_auth_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target user % does not exist in authentication engine.', p_auth_user_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- 5. Assert caller phone has been confirmed in authentication engine
    IF v_auth_phone IS NULL OR v_phone_confirmed_at IS NULL THEN
        RAISE EXCEPTION 'Authenticated caller phone number is unconfirmed or missing in authentication engine.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 6. Verified Phone Number Matching against auth.users
    IF regexp_replace(v_auth_phone, '^\+', '') IS DISTINCT FROM regexp_replace(v_req.new_phone_e164, '^\+', '') THEN
        RAISE EXCEPTION 'Authenticated account phone does not match approved recovery phone.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 7. Ensure caller row exists in public.users WITH ROW LOCK
    SELECT * INTO v_new_user FROM public.users WHERE id = p_auth_user_id FOR UPDATE;
    IF v_new_user.id IS NULL THEN
        INSERT INTO public.users (id, phone_e164, role, is_active)
        VALUES (p_auth_user_id, v_req.new_phone_e164, 'patient', TRUE)
        ON CONFLICT (id) DO UPDATE SET phone_e164 = EXCLUDED.phone_e164
        RETURNING * INTO v_new_user;
    END IF;

    -- 8. Verified Phone Number Matching against public.users
    IF v_req.new_phone_e164 IS DISTINCT FROM v_new_user.phone_e164 THEN
        RAISE EXCEPTION 'Verified caller phone number does not match approved recovery phone number.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- 9. Prevent caller from already owning another distinct profile
    IF EXISTS (
        SELECT 1 FROM public.patient_profiles 
        WHERE user_id = p_auth_user_id AND id != v_req.patient_profile_id
    ) THEN
        RAISE EXCEPTION 'Authenticated account already owns another patient profile.'
            USING ERRCODE = 'unique_violation';
    END IF;

    -- 10. Authoritative derivation of phone hash in SQL (caller cannot forge)
    v_derived_phone_hash := encode(sha256(v_req.new_phone_e164::bytea), 'hex');
    IF p_new_phone_hash IS NOT NULL AND p_new_phone_hash != '' AND p_new_phone_hash != v_derived_phone_hash THEN
        RAISE EXCEPTION 'Phone checksum mismatch.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 11. Unique Phone Hash Collision Check on other profiles
    IF EXISTS (
        SELECT 1 FROM public.patient_profiles 
        WHERE phone_hash = v_derived_phone_hash AND id != v_req.patient_profile_id
    ) THEN
        RAISE EXCEPTION 'Target phone number is already registered to another patient profile.'
            USING ERRCODE = 'unique_violation';
    END IF;

    -- 12. Lock target patient profile
    SELECT * INTO v_profile FROM public.patient_profiles 
    WHERE id = v_req.patient_profile_id FOR UPDATE;

    SELECT role INTO v_actor_role FROM public.users WHERE id = p_auth_user_id;
    IF v_actor_role IS NULL THEN
        v_actor_role := 'patient';
    END IF;

    -- 13. Re-link profile to new authenticated account under narrow transaction-local authorization
    PERFORM set_config('app.in_account_recovery', 'true', true);

    UPDATE public.patient_profiles 
    SET user_id = p_auth_user_id, phone_hash = v_derived_phone_hash, updated_at = NOW()
    WHERE id = v_req.patient_profile_id;

    PERFORM set_config('app.in_account_recovery', 'false', true);

    -- 14. Mark request completed
    UPDATE public.patient_recovery_requests SET status = 'completed' WHERE id = v_req.id;

    -- 15. Emit audit record in same transaction
    INSERT INTO public.audit_logs (
        actor_user_id, actor_role, action, entity_type, entity_id, ip_address, details
    ) VALUES (
        p_auth_user_id, v_actor_role, 'patient_account_recovered', 'patient_profile', v_req.patient_profile_id::text, p_ip_address,
        jsonb_build_object(
            'recovery_request_id', p_recovery_request_id,
            'old_phone_hash', v_req.old_phone_hash,
            'request_id', p_request_id,
            'outcome', 'success'
        )
    );

    RETURN jsonb_build_object(
        'success', true,
        'patient_id', v_profile.patient_id,
        'message', 'Account successfully recovered. All medical records remain linked to your Patient ID.'
    );
END;
$$;

REVOKE ALL ON FUNCTION public.verify_account_recovery_atomic FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.verify_account_recovery_atomic TO service_role, postgres;


-- ------------------------------------------------------------------------------
-- 3. REFINED ROW-LOCK FOR ATOMIC MEDICAL REPORT DELETION
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
    -- 1. Fetch report owned strictly by caller with targeted row lock on medical_reports only
    SELECT mr.* INTO v_report 
    FROM public.medical_reports mr
    JOIN public.patient_profiles pp ON pp.id = mr.patient_id
    WHERE mr.id = p_report_id AND pp.user_id = p_auth_user_id
    FOR UPDATE OF mr;

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
