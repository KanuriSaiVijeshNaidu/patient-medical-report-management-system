"""Database and Supabase client factory.

Note: Credentials must be configured in environment variables.
In development without credentials, client initialization remains safe.
"""
from typing import Optional
from supabase import create_client, Client
from app.core.config import settings

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """Returns initialized privileged Supabase service-role client if configured."""
    global _supabase_client
    if settings.SUPABASE_URL and settings.active_supabase_key:
        expected_header = f"Bearer {settings.active_supabase_key}"
        if _supabase_client is not None:
            # Guarantee service-role Authorization header is never mutated by auth sessions
            if _supabase_client.options.headers.get("Authorization") != expected_header:
                _supabase_client.options.headers["Authorization"] = expected_header
                if hasattr(_supabase_client, "auth") and hasattr(_supabase_client.auth, "_headers"):
                    _supabase_client.auth._headers["Authorization"] = expected_header
                _supabase_client._postgrest = None
            return _supabase_client

        try:
            _supabase_client = create_client(
                settings.SUPABASE_URL,
                settings.active_supabase_key
            )
            return _supabase_client
        except Exception:
            # Safe fallback if credentials invalid
            return None
    return None


def create_isolated_auth_client() -> Optional[Client]:
    """Creates a new, unshared Supabase client for GoTrue auth operations
    (like password verification), ensuring the singleton service-role client
    is never polluted with user auth tokens.
    """
    if settings.SUPABASE_URL and settings.active_supabase_key:
        try:
            return create_client(
                settings.SUPABASE_URL,
                settings.active_supabase_key
            )
        except Exception:
            return None
    return None


def reset_supabase_client() -> None:
    """Resets the cached Supabase client singleton."""
    global _supabase_client
    _supabase_client = None


def is_db_configured() -> bool:
    """Checks whether database credentials are provided."""
    return bool(settings.SUPABASE_URL and settings.active_supabase_key)

