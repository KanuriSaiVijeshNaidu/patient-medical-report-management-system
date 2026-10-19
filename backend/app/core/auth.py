from typing import Optional
from uuid import UUID
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.core.config import settings
from app.core.database import get_supabase_client, is_db_configured

security_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    id: UUID
    phone: Optional[str] = None
    email: Optional[str] = None
    role: str = "patient"
    is_authenticated: bool = True


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> AuthenticatedUser:
    """Validates the incoming Supabase JWT Bearer token and extracts the authenticated user.

    Ensures that caller identity is strictly derived from the verified cryptographic token,
    never from unverified client-supplied parameters.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Case 1: Supabase client is configured and can verify or decode token
    # Supabase tokens can be validated via jwt with SUPABASE_JWT_SECRET if provided,
    # or by calling supabase auth client.
    client = get_supabase_client()
    if client:
        try:
            # Verify token via Supabase Auth API
            user_response = client.auth.get_user(token)
            if user_response and user_response.user:
                u = user_response.user
                return AuthenticatedUser(
                    id=UUID(u.id),
                    phone=getattr(u, "phone", None),
                    email=getattr(u, "email", None),
                    role=u.user_metadata.get("role", "patient") if hasattr(u, "user_metadata") and u.user_metadata else "patient",
                )
        except Exception:
            # If network verification fails, attempt direct JWT decode if JWT secret configured
            pass

    # Direct JWT verification fallback if secret is known
    jwt_secret = settings.SUPABASE_JWT_SECRET or settings.JWT_SECRET_KEY
    if jwt_secret and jwt_secret != "insecure-development-secret-key-replace-in-production":
        try:
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            sub = payload.get("sub")
            if sub:
                return AuthenticatedUser(
                    id=UUID(sub),
                    phone=payload.get("phone"),
                    email=payload.get("email"),
                    role=payload.get("role", "patient"),
                )
        except (jwt.PyJWTError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # If Supabase is not configured and no valid secret is present:
    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unconfigured. Please configure SUPABASE_URL and SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unable to verify authentication token with identity provider.",
        headers={"WWW-Authenticate": "Bearer"},
    )
