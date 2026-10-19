import hashlib
import secrets


def hash_token(token: str) -> str:
    """Hashes a raw grant token using SHA-256 for secure database lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_share_token() -> str:
    """Generates a high-entropy URL-safe share token."""
    return secrets.token_urlsafe(32)


def hash_phone(phone_e164: str) -> str:
    """Generates a consistent SHA-256 hash of normalized phone number for deduplication checks."""
    normalized = phone_e164.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
