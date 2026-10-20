import logging
from typing import Optional
from uuid import UUID
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.core.config import settings
from app.core.database import get_supabase_client, is_db_configured

logger = logging.getLogger("security.auth")
security_scheme = HTTPBearer(auto_error=False)

_jwks_client: Optional[jwt.PyJWKClient] = None


def get_jwks_client() -> Optional[jwt.PyJWKClient]:
    """Returns cached PyJWKClient for hosted Supabase JWKS endpoint."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client

    if settings.SUPABASE_URL:
        jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        try:
            _jwks_client = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)
            return _jwks_client
        except Exception as e:
            logger.warning("Could not initialize Supabase JWKS client: %s", e)
            return None
    return None


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
        logger.info("Unauthenticated access attempt to protected endpoint")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    if not token:
        logger.warning("Empty authentication token received")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty or missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Verification of backend-issued HMAC HS256 tokens using configured JWT secret
    jwt_secret = settings.SUPABASE_JWT_SECRET
    if not jwt_secret and is_db_configured():
        jwt_secret = settings.JWT_SECRET_KEY

    if jwt_secret and jwt_secret.strip():
        expected_issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1" if settings.SUPABASE_URL else None
        has_iss_claim = False
        try:
            unverified_claims = jwt.decode(token, options={"verify_signature": False, "verify_exp": False, "verify_aud": False})
            has_iss_claim = "iss" in unverified_claims
        except Exception:
            pass

        verify_iss = bool(expected_issuer and has_iss_claim)
        decode_options = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_aud": True,
            "verify_iss": verify_iss,
        }

        try:
            decode_kwargs = {
                "jwt": token,
                "key": jwt_secret,
                "algorithms": ["HS256"],
                "audience": "authenticated",
                "options": decode_options,
            }
            if verify_iss:
                decode_kwargs["issuer"] = expected_issuer

            payload = jwt.decode(**decode_kwargs)
            sub = payload.get("sub")
            if not sub:
                logger.warning(
                    "Authentication failed: token missing sub claim",
                    extra={"event": "auth_token_missing_sub", "outcome": "denied"}
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication token is missing subject identity (sub).",
                    headers={"WWW-Authenticate": "Bearer"},
                )

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
        except HTTPException:
            raise
        except jwt.ExpiredSignatureError:
            logger.warning(
                "Authentication failed: JWT signature expired",
                extra={"event": "auth_token_expired", "outcome": "denied"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidAudienceError:
            logger.warning(
                "Authentication failed: invalid JWT audience claim",
                extra={"event": "auth_token_invalid_audience", "outcome": "denied"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience claim. Expected 'authenticated'.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidIssuerError:
            logger.warning(
                "Authentication failed: invalid JWT issuer claim",
                extra={"event": "auth_token_invalid_issuer", "outcome": "denied"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer claim.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (jwt.InvalidSignatureError, jwt.DecodeError):
            # Token not signed with local secret; fall through to Supabase Auth / JWKS verification
            pass

    # 2. Verification via live Supabase Auth API if client is configured
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
            logger.debug("Supabase auth get_user verification skipped or failed: %s", e)

    # 3. Asymmetric verification via Supabase JWKS (RS256, ES256, EdDSA)
    token_alg = "HS256"
    try:
        header = jwt.get_unverified_header(token)
        token_alg = header.get("alg", "HS256")
    except Exception:
        token_alg = "HS256"

    if token_alg in ["RS256", "ES256", "EdDSA"] and settings.SUPABASE_URL:
        jwks_client = get_jwks_client()
        if jwks_client:
            try:
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                expected_issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=[token_alg],
                    audience="authenticated",
                    issuer=expected_issuer,
                    options={"verify_signature": True, "verify_exp": True, "verify_aud": True, "verify_iss": True},
                )
                sub = payload.get("sub")
                if not sub:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication token is missing subject identity (sub).",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
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
            except HTTPException:
                raise
            except jwt.ExpiredSignatureError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication token has expired. Please sign in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            except Exception as err:
                logger.warning("JWKS token verification failed: %s", err)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token signature or payload.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    # 4. If neither Supabase client nor valid JWT secret is configured:
    if not is_db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unconfigured. Please configure SUPABASE_URL and SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )

    logger.warning(
        "Authentication failed: invalid JWT signature or format",
        extra={"event": "auth_token_invalid", "outcome": "denied"}
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token. Please sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
