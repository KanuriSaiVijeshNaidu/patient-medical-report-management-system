import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ENVIRONMENT: str = "development"
    PORT: int = 8000
    DEBUG: bool = True
    ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    )
    CORS_ORIGIN_REGEX: str = r"^https:\/\/([a-zA-Z0-9_-]+\.)*vercel\.app$"

    # Supabase credentials (populated in environment)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SECRET_KEY: str = ""
    DATABASE_URL: str = ""

    # Storage & Share settings
    STORAGE_BUCKET_NAME: str = "medical-reports"
    SIGNED_URL_EXPIRATION_SECONDS: int = 300
    MAX_REPORT_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB default
    DEFAULT_SHARE_EXPIRATION_SECONDS: int = 900  # 15 minutes default
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # JWT Settings
    JWT_SECRET_KEY: str = "insecure-development-secret-key-replace-in-production"
    JWT_ALGORITHM: str = "HS256"

    def model_post_init(self, __context) -> None:
        """Post-initialization to normalize environment and production flags."""
        # Detect production mode from ENVIRONMENT, ENV, APP_ENV, or RENDER platform
        detected_env = (
            os.getenv("ENVIRONMENT")
            or os.getenv("ENV")
            or os.getenv("APP_ENV")
        )
        if detected_env:
            self.ENVIRONMENT = detected_env.strip().lower()
        elif os.getenv("RENDER") in ("true", "1", "True") and self.ENVIRONMENT == "development":
            self.ENVIRONMENT = "production"

        if self.ENVIRONMENT in ("production", "prod"):
            # In production, debug defaults to False unless explicitly set True
            debug_env = os.getenv("DEBUG")
            if debug_env is None:
                self.DEBUG = False

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod")

    @property
    def is_supabase_configured(self) -> bool:
        return bool(
            self.SUPABASE_URL
            and (
                self.SUPABASE_SERVICE_ROLE_KEY
                or self.SUPABASE_SECRET_KEY
                or self.SUPABASE_KEY
                or self.SUPABASE_ANON_KEY
                or self.SUPABASE_PUBLISHABLE_KEY
            )
        )

    @property
    def active_supabase_key(self) -> str:
        return (
            self.SUPABASE_SERVICE_ROLE_KEY
            or self.SUPABASE_SECRET_KEY
            or self.SUPABASE_KEY
            or self.SUPABASE_ANON_KEY
            or self.SUPABASE_PUBLISHABLE_KEY
        )

    @property
    def cors_origins(self) -> List[str]:
        """Parses comma-separated ALLOWED_ORIGINS into a clean, normalized list of origins.

        Trims whitespace, strips wrapping quotes, normalizes trailing slashes,
        and ensures no comma-separated origins are left concatenated.
        """
        raw = self.ALLOWED_ORIGINS
        default_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ]
        if not raw:
            return default_origins

        origins: List[str] = []
        items = raw if isinstance(raw, list) else str(raw).split(",")
        for item in items:
            cleaned = str(item).strip().strip("'\"").rstrip("/")
            if cleaned:
                origins.append(cleaned)

        return origins or default_origins

    @property
    def effective_cors_origins(self) -> List[str]:
        """Combines ALLOWED_ORIGINS, FRONTEND_BASE_URL, and production domains for CORS middleware."""
        origins = list(self.cors_origins)
        if self.FRONTEND_BASE_URL:
            cleaned_frontend = str(self.FRONTEND_BASE_URL).strip().strip("'\"").rstrip("/")
            if cleaned_frontend and cleaned_frontend not in origins:
                origins.append(cleaned_frontend)
        production_vercel = "https://patient-medical-report-management-s-taupe.vercel.app"
        if production_vercel not in origins:
            origins.append(production_vercel)
        return origins


settings = Settings()
