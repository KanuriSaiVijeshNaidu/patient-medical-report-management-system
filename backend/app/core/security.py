import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID
import bcrypt
import jwt
from app.core.config import settings

# Ambiguity-free alphanumeric alphabet (excluding 0, O, 1, I to prevent read errors)
PATIENT_ID_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_patient_id(year: Optional[int] = None) -> str:
    """Generates a permanent, collision-resistant, human-readable Patient ID.

    Format: MED-YYYY-XXXXXX (e.g. MED-2026-8K4F29)
    """
    current_year = year or datetime.now().year
    random_chars = "".join(secrets.choice(PATIENT_ID_ALPHABET) for _ in range(6))
    return f"MED-{current_year}-{random_chars}"


def generate_report_id(year: Optional[int] = None) -> str:
    """Generates a collision-resistant, human-readable Medical Report ID.

    Format: REP-YYYY-XXXXXX (e.g. REP-2026-8K4F29)
    """
    current_year = year or datetime.now().year
    random_chars = "".join(secrets.choice(PATIENT_ID_ALPHABET) for _ in range(6))
    return f"REP-{current_year}-{random_chars}"


def normalize_phone(phone: str) -> str:
    """Normalizes phone number to E.164-compatible clean representation."""
    cleaned = "".join(c for c in phone.strip() if c.isdigit() or c == "+")
    if not cleaned.startswith("+"):
        # Assume Indian country code +91 if 10 digits provided without country code
        if len(cleaned) == 10:
            cleaned = "+91" + cleaned
        else:
            cleaned = "+" + cleaned
    return cleaned


def hash_phone(phone: str) -> str:
    """Generates a consistent SHA-256 hash of normalized phone number for deduplication checks."""
    normalized = normalize_phone(phone)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def mask_phone(phone: str) -> str:
    """Masks phone number for secure display, preserving country code and last 4 digits."""
    norm = normalize_phone(phone)
    if len(norm) > 6:
        prefix = norm[:3]
        suffix = norm[-4:]
        masked_middle = "*" * (len(norm) - 7)
        return f"{prefix} {masked_middle} {suffix}"
    return norm


def hash_token(token: str) -> str:
    """Hashes a raw grant token using SHA-256 for secure database lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_share_token() -> str:
    """Generates a high-entropy URL-safe share token."""
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt with salt generation."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    user_id: UUID,
    role: str = "patient",
    username: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generates a cryptographically signed JWT Bearer token compatible with Supabase Auth."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=24))
    secret = settings.SUPABASE_JWT_SECRET or settings.JWT_SECRET_KEY

    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "role": "authenticated",
        "app_metadata": {"role": role, "provider": "username_password"},
        "user_metadata": {"username": username} if username else {},
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if settings.SUPABASE_URL:
        payload["iss"] = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"

    return jwt.encode(payload, secret, algorithm="HS256")
