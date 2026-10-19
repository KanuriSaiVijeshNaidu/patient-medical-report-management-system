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

    Enforces cryptographic validation including:
    - Signature integrity
    - Expiration time (exp)
    - Audience claim ('authenticated')
    - Issuer claim (matching Supabase project URL if configured)
    - Non-empty subject UUID (sub)

    Ensures patient identity is derived strictly from verified credentials,
    never trusted from client-supplied body or query parameters.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty or missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Verification via live Supabase Auth API if client is configured
    client = get_supabase_client()
    if client:
        try:
            user_response = client.auth.get_user(token)
            if user_response and user_response.user:
                u = user_response.user
                return AuthenticatedUser(
                    id=UUID(u.id),
                    phone=getattr(u, "phone", None),
                    email=getattr(u, "email", None),
                    role=u.user_metadata.get("role", "patient") if hasattr(u, "user_metadata") and u.user_metadata else "patient",
                )
        except Exception as e:
            err_str = str(e).lower()
            # If the Supabase Auth server explicitly rejected the token
            status_code = getattr(e, "status", None) or getattr(e, "code", None)
            is_auth_rejection = (
                status_code in [400, 401, 403]
                or any(keyword in err_str for keyword in [
                    "invalid", "expired", "jwt", "unauthorized", "signature", "malformed", "not found"
                ])
            )
            if is_auth_rejection:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired authentication token.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            # If network/connectivity error (e.g. timeout, DNS, connection refused), fall through to JWT secret verification
            pass

    # 2. Cryptographic JWT verification using SUPABASE_JWT_SECRET
    jwt_secret = settings.SUPABASE_JWT_SECRET
    if jwt_secret and jwt_secret.strip():
        expected_issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1" if settings.SUPABASE_URL else None
        decode_options = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_aud": True,
            "verify_iss": bool(expected_issuer),
        }

        try:
            decode_kwargs = {
                "jwt": token,
                "key": jwt_secret,
                "algorithms": ["HS256"],
                "audience": "authenticated",
                "options": decode_options,
            }
            if expected_issuer:
                decode_kwargs["issuer"] = expected_issuer

            payload = jwt.decode(**decode_kwargs)

            sub = payload.get("sub")
            if not sub:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication token is missing subject identity (sub).",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # In Supabase JWTs, role is typically 'authenticated'
            # Custom roles may be in app_metadata or user_metadata
            app_meta = payload.get("app_metadata", {})
            user_meta = payload.get("user_metadata", {})
            user_role = (
                app_meta.get("role")
                or user_meta.get("role")
                or payload.get("role")
                or "patient"
            )

            return AuthenticatedUser(
                id=UUID(sub),
                phone=payload.get("phone") or user_meta.get("phone"),
                email=payload.get("email"),
                role=user_role,
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidAudienceError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience claim. Expected 'authenticated'.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidIssuerError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer claim.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (jwt.PyJWTError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token signature or payload.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 3. If neither Supabase client nor valid JWT secret is configured:
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
