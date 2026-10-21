-- ==============================================================================
-- Migration: 20261021000001_support_photo_uploads_and_40mb_limit.sql
-- Description:
--   1. Updates 'medical-reports' storage bucket to accept 40 MB files (41,943,040 bytes).
--   2. Expands allowed MIME types to include PDF, JPEG, and PNG images.
--   3. Preserves private access and authorized Row Level Security policies.
-- ==============================================================================

UPDATE storage.buckets
SET
    file_size_limit = 41943040, -- 40 MB in bytes
    allowed_mime_types = ARRAY['application/pdf', 'image/jpeg', 'image/png']::text[]
WHERE id = 'medical-reports';

-- Ensure bucket exists with proper settings if newly initialized
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'medical-reports',
    'medical-reports',
    false,
    41943040,
    ARRAY['application/pdf', 'image/jpeg', 'image/png']::text[]
)
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = 41943040,
    allowed_mime_types = ARRAY['application/pdf', 'image/jpeg', 'image/png']::text[];
