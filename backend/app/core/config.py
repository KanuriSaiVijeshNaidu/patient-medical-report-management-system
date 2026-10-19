from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ENVIRONMENT: str = "development"
    PORT: int = 8000
    DEBUG: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Supabase credentials (populated in environment)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # Storage settings
    STORAGE_BUCKET_NAME: str = "medical-reports"
    SIGNED_URL_EXPIRATION_SECONDS: int = 300

    # JWT Settings
    JWT_SECRET_KEY: str = "insecure-development-secret-key-replace-in-production"
    JWT_ALGORITHM: str = "HS256"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()
