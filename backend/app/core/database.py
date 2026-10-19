"""Database and Supabase client factory.

Note: Credentials must be configured in environment variables.
In development without credentials, client initialization remains safe.
"""
from typing import Optional
from supabase import create_client, Client
from app.core.config import settings

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """Returns initialized Supabase client if configured."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    if settings.SUPABASE_URL and settings.active_supabase_key:
        try:
            _supabase_client = create_client(
                settings.SUPABASE_URL,
                settings.active_supabase_key
            )
            return _supabase_client
        except Exception as e:
            # Safe fallback if credentials invalid
            return None
    return None


def is_db_configured() -> bool:
    """Checks whether database credentials are provided."""
    return bool(settings.SUPABASE_URL and settings.active_supabase_key)

