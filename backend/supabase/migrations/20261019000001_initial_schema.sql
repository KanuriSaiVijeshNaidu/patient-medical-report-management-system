-- ==============================================================================
-- Initial Schema Migration: Patient Medical Report Management System
-- Version: 20261019000001
-- Engine: PostgreSQL 15+ / Supabase
-- Description: Core tables, relationships, indexes, and Row-Level Security policies
-- ==============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------------------------
-- 1. USERS TABLE (Application Profile Mapping)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE,
    phone_e164 VARCHAR(20),
    role VARCHAR(32) NOT NULL CHECK (role IN ('patient', 'hospital_staff', 'platform_admin')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 2. PATIENT PROFILES
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.patient_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id VARCHAR(32) UNIQUE NOT NULL, -- e.g. MED-2026-894102
    user_id UUID UNIQUE NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    full_name VARCHAR(150) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(20) NOT NULL CHECK (gender IN ('male', 'female', 'other', 'prefer_not_to_say')),
    blood_group VARCHAR(5) CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    emergency_contact_phone VARCHAR(20),
    phone_hash VARCHAR(64) NOT NULL, -- SHA-256 for duplicate matching
    masked_aadhaar_ref VARCHAR(20),  -- e.g. XXXX-XXXX-1234, raw Aadhaar NEVER stored
    verification_status VARCHAR(32) NOT NULL DEFAULT 'unverified' 
        CHECK (verification_status IN ('unverified', 'phone_verified', 'kyc_verified')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 3. HOSPITALS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hospitals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    registration_number VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    hospital_type VARCHAR(50) NOT NULL 
        CHECK (hospital_type IN ('clinic', 'general_hospital', 'diagnostic_lab', 'multi_specialty')),
    contact_phone VARCHAR(20) NOT NULL,
    contact_email VARCHAR(255) NOT NULL,
    address JSONB NOT NULL DEFAULT '{}'::jsonb,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'pending' 
        CHECK (verification_status IN ('pending', 'verified', 'suspended')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 4. HOSPITAL STAFF
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hospital_staff (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    hospital_id UUID NOT NULL REFERENCES public.hospitals(id) ON DELETE CASCADE,
    employee_id VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL 
        CHECK (role IN ('clinician', 'radiologist', 'lab_technician', 'records_clerk', 'administrator')),
    department VARCHAR(100) NOT NULL,
    clinical_registration_number VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 5. MEDICAL REPORTS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.medical_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id VARCHAR(32) UNIQUE NOT NULL, -- e.g. REP-2026-471092
    patient_id UUID NOT NULL REFERENCES public.patient_profiles(id) ON DELETE RESTRICT,
    hospital_id UUID REFERENCES public.hospitals(id) ON DELETE SET NULL,
    uploaded_by_staff_id UUID REFERENCES public.hospital_staff(id) ON DELETE SET NULL,
    upload_source VARCHAR(20) NOT NULL CHECK (upload_source IN ('patient', 'hospital')),
    title VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL 
        CHECK (category IN ('blood_test', 'xray', 'ct_scan', 'mri', 'prescription', 'discharge_summary', 'other')),
    report_date DATE NOT NULL,
    file_storage_path TEXT NOT NULL,
    file_checksum_sha256 VARCHAR(64) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'unverified' 
        CHECK (verification_status IN ('unverified', 'hospital_verified')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 6. RECORD ACCESS GRANTS (Expiring QR Code & Link Sharing)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.record_access_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES public.patient_profiles(id) ON DELETE CASCADE,
    grant_token_hash VARCHAR(64) UNIQUE NOT NULL, -- SHA-256 of the token
    scope VARCHAR(32) NOT NULL DEFAULT 'all' CHECK (scope IN ('all', 'specific_reports')),
    report_ids UUID[] NOT NULL DEFAULT '{}'::uuid[],
    recipient_hospital_id UUID REFERENCES public.hospitals(id) ON DELETE SET NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    max_uses INTEGER,
    expires_at TIMESTAMPTZ NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 7. EMERGENCY ACCESS LOGS (Break-Glass Audit Trail)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.emergency_access_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES public.patient_profiles(id) ON DELETE RESTRICT,
    hospital_id UUID NOT NULL REFERENCES public.hospitals(id) ON DELETE RESTRICT,
    accessed_by_staff_id UUID NOT NULL REFERENCES public.hospital_staff(id) ON DELETE RESTRICT,
    reason_category VARCHAR(50) NOT NULL 
        CHECK (reason_category IN ('unconscious_patient', 'trauma_resuscitation', 'acute_cardiac_arrest', 'other_life_threatening')),
    clinical_justification TEXT NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    accessed_report_ids UUID[] NOT NULL DEFAULT '{}'::uuid[],
    review_status VARCHAR(32) NOT NULL DEFAULT 'pending' 
        CHECK (review_status IN ('pending', 'reviewed_compliant', 'flagged_audit')),
    reviewed_by_staff_id UUID REFERENCES public.hospital_staff(id) ON DELETE SET NULL,
    review_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 8. PATIENT RECOVERY REQUESTS (Phone Number Updates Without Duplicate Profiles)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.patient_recovery_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_profile_id UUID NOT NULL REFERENCES public.patient_profiles(id) ON DELETE CASCADE,
    old_phone_hash VARCHAR(64) NOT NULL,
    new_phone_e164 VARCHAR(20) NOT NULL,
    recovery_channel VARCHAR(50) NOT NULL 
        CHECK (recovery_channel IN ('email_challenge', 'hospital_desk', 'identity_doc')),
    status VARCHAR(32) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'verified', 'rejected')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 9. AUDIT LOGS (Immutable Security and Access Records)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    actor_role VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    user_agent TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- INDEXES
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_patient_profiles_patient_id ON public.patient_profiles(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_profiles_phone_hash ON public.patient_profiles(phone_hash);
CREATE INDEX IF NOT EXISTS idx_patient_profiles_user_id ON public.patient_profiles(user_id);

CREATE INDEX IF NOT EXISTS idx_medical_reports_patient_id ON public.medical_reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_medical_reports_category ON public.medical_reports(patient_id, category);
CREATE INDEX IF NOT EXISTS idx_medical_reports_hospital_id ON public.medical_reports(hospital_id);
CREATE INDEX IF NOT EXISTS idx_medical_reports_created_at ON public.medical_reports(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_record_access_grants_hash ON public.record_access_grants(grant_token_hash) 
    WHERE is_revoked = FALSE;

CREATE INDEX IF NOT EXISTS idx_hospital_staff_user ON public.hospital_staff(user_id);
CREATE INDEX IF NOT EXISTS idx_hospital_staff_hospital ON public.hospital_staff(hospital_id);

CREATE INDEX IF NOT EXISTS idx_emergency_access_patient ON public.emergency_access_logs(patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON public.audit_logs(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON public.audit_logs(entity_type, entity_id);

-- ------------------------------------------------------------------------------
-- ROW-LEVEL SECURITY (RLS) POLICIES
-- ------------------------------------------------------------------------------

-- Enable RLS on core tables
ALTER TABLE public.patient_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.medical_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.record_access_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emergency_access_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- Patient Profiles: Patients can select and update their own profile
CREATE POLICY "Patients view own profile"
    ON public.patient_profiles FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Patients update own profile"
    ON public.patient_profiles FOR UPDATE
    USING (auth.uid() = user_id);

-- Medical Reports: Patients can view reports belonging to their profile
CREATE POLICY "Patients view own reports"
    ON public.medical_reports FOR SELECT
    USING (
        patient_id IN (
            SELECT id FROM public.patient_profiles WHERE user_id = auth.uid()
        )
    );

-- Medical Reports: Hospital staff can view reports issued by their own hospital
CREATE POLICY "Hospital staff view hospital reports"
    ON public.medical_reports FOR SELECT
    USING (
        hospital_id IN (
            SELECT hospital_id FROM public.hospital_staff 
            WHERE user_id = auth.uid() AND is_active = TRUE
        )
    );

-- Record Access Grants: Patients can manage their own grants
CREATE POLICY "Patients manage own access grants"
    ON public.record_access_grants FOR ALL
    USING (
        patient_id IN (
            SELECT id FROM public.patient_profiles WHERE user_id = auth.uid()
        )
    );

-- Audit Logs & Emergency Access Logs: Read-only for actors, insert-only
CREATE POLICY "Authenticated users insert audit logs"
    ON public.audit_logs FOR INSERT
    WITH CHECK (auth.uid() IS NOT NULL);

CREATE POLICY "Hospital staff insert emergency access"
    ON public.emergency_access_logs FOR INSERT
    WITH CHECK (
        accessed_by_staff_id IN (
            SELECT id FROM public.hospital_staff WHERE user_id = auth.uid() AND is_active = TRUE
        )
    );
