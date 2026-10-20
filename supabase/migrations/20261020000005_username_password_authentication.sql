-- ==============================================================================
-- Support Username & Password Authentication
-- Version: 20261020000005
-- Engine: PostgreSQL 15+ / Supabase
-- Description:
--   1. Adds username column to public.users with a case-insensitive unique index.
--   2. Creates dedicated public.user_credentials table to securely isolate bcrypt
--      password hashes away from demographic/patient profile data.
--   3. Enforces strict Row Level Security (RLS) on user_credentials, restricting
--      all read/write permissions to service_role and postgres only.
--   4. Preserves all existing patient records, Patient IDs, RLS policies, and audit trails.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. ADD USERNAME COLUMN TO public.users
-- ------------------------------------------------------------------------------
ALTER TABLE public.users 
    ADD COLUMN IF NOT EXISTS username VARCHAR(50);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower 
    ON public.users (LOWER(username)) 
    WHERE username IS NOT NULL;

-- ------------------------------------------------------------------------------
-- 2. CREATE ISOLATED USER CREDENTIALS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Case-insensitive unique index for fast lookup and duplicate prevention
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_credentials_username_lower 
    ON public.user_credentials (LOWER(username));

CREATE INDEX IF NOT EXISTS idx_user_credentials_user_id 
    ON public.user_credentials (user_id);

-- ------------------------------------------------------------------------------
-- 3. ROW-LEVEL SECURITY & PERMISSION RESTRICTIONS
-- ------------------------------------------------------------------------------
ALTER TABLE public.user_credentials ENABLE ROW LEVEL SECURITY;

-- Deny all client-side access via PostgREST/anon/authenticated roles
-- Only verified backend service_role / postgres functions can access credentials
REVOKE ALL ON public.user_credentials FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.user_credentials TO service_role, postgres;
