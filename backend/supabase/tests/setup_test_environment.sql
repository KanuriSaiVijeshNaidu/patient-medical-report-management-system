-- ==============================================================================
-- Isolated Test Environment Setup Harness
-- Version: 1.0.0
-- Purpose:
--   Enables running migrations and RLS tests in an isolated local PostgreSQL database
--   without requiring a full remote Supabase project.
--   Emulates Supabase's auth schema, JWT claim functions (auth.uid, auth.role),
--   and default PostgreSQL roles (anon, authenticated, service_role).
-- ==============================================================================

-- 1. Create required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Create Supabase Auth schema
CREATE SCHEMA IF NOT EXISTS auth;

-- 3. Emulate auth.users table for foreign key validation
CREATE TABLE IF NOT EXISTS auth.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE,
    encrypted_password VARCHAR(255),
    email_confirmed_at TIMESTAMPTZ,
    phone VARCHAR(20) UNIQUE,
    phone_confirmed_at TIMESTAMPTZ,
    role VARCHAR(50) DEFAULT 'authenticated',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Create standard Supabase database roles if they do not exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN BYPASSRLS;
    END IF;
END $$;

-- 5. Emulate auth.uid() function (reads session variable 'request.jwt.claim.sub')
CREATE OR REPLACE FUNCTION auth.uid()
RETURNS UUID AS $$
BEGIN
    RETURN NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- 6. Emulate auth.role() function (reads session variable 'request.jwt.claim.role')
CREATE OR REPLACE FUNCTION auth.role()
RETURNS TEXT AS $$
BEGIN
    RETURN NULLIF(current_setting('request.jwt.claim.role', true), '');
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- 7. Grant schema usage to roles
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
