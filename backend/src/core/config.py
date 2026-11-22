"""
Application Configuration and Environment Validation.
Enforces fail-fast secret checks in staging and production environments.
"""

import base64
import binascii
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_PLACEHOLDER = "dev-only-jwt-secret-key-change-before-staging-or-prod-32bytes"
_DEV_AES_PLACEHOLDER = "ZGV2LW9ubHktMzItYnl0ZS1hZXMta2V5LWNoYW5nZSE="
_KNOWN_WEAK_SECRETS = {
    _DEV_JWT_PLACEHOLDER,
    _DEV_AES_PLACEHOLDER,
    "CHANGE_IN_PRODUCTION_SUPER_SECRET_KEY_MIN_32_BYTES_LONG",
    "w14R57h7dGf2038mKjLp901qZaXcvBnMlkjhgfdsaQW=",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Enterprise CRM Engine"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Literal["development", "test", "staging", "production"] = "development"

    # PostgreSQL Connection (asyncpg)
    DATABASE_URL: str = "postgresql+asyncpg://crm_app:crm_app_dev_pass@localhost:5432/crm_enterprise_db"
    MIGRATION_DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # Redis Connection & Distributed Rate Limiting
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_ENABLED: bool = True

    # JWT Authentication & Refresh Token Lifecycle
    JWT_SECRET_KEY: str = _DEV_JWT_PLACEHOLDER
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_COOKIE_SECURE: bool | None = None

    # Data Encryption at Rest (AES-256-GCM symmetric key, base64-encoded 32 bytes)
    APPLICATION_ENCRYPTION_KEY_B64: str = _DEV_AES_PLACEHOLDER

    # CORS & Security
    ALLOWED_HOSTS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # AI Model Providers & Offline Stub Policy
    GEMINI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini/gemini-3.8-flash"
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    OPENAI_MODEL: str = "gpt-4o"
    DEFAULT_LLM_PROVIDER: Literal["gemini", "claude", "openai"] = "gemini"
    ALLOW_OFFLINE_AI_STUB: bool | None = None

    @property
    def allow_offline_stub(self) -> bool:
        if self.ALLOW_OFFLINE_AI_STUB is not None:
            return self.ALLOW_OFFLINE_AI_STUB
        return self.ENVIRONMENT in ("development", "test")

    @property
    def cookie_secure(self) -> bool:
        if self.AUTH_COOKIE_SECURE is not None:
            return self.AUTH_COOKIE_SECURE
        return self.ENVIRONMENT in ("staging", "production")

    @model_validator(mode="after")
    def validate_security_posture(self) -> "Settings":
        try:
            aes_bytes = base64.b64decode(self.APPLICATION_ENCRYPTION_KEY_B64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("APPLICATION_ENCRYPTION_KEY_B64 must be valid base64") from exc

        if len(aes_bytes) != 32:
            raise ValueError("APPLICATION_ENCRYPTION_KEY_B64 must decode to exactly 32 bytes (256 bits)")

        if len(self.JWT_SECRET_KEY.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 bytes long")

        if self.ENVIRONMENT in ("staging", "production"):
            if self.JWT_SECRET_KEY in _KNOWN_WEAK_SECRETS:
                raise ValueError(
                    "JWT_SECRET_KEY cannot use a default/placeholder key in staging or production"
                )
            if self.APPLICATION_ENCRYPTION_KEY_B64 in _KNOWN_WEAK_SECRETS:
                raise ValueError(
                    "APPLICATION_ENCRYPTION_KEY_B64 cannot use a default/placeholder key in staging or production"
                )
            if "*" in self.ALLOWED_HOSTS:
                raise ValueError("ALLOWED_HOSTS cannot contain wildcard '*' when allow_credentials=True")
            if self.ALLOW_OFFLINE_AI_STUB is True:
                raise ValueError("ALLOW_OFFLINE_AI_STUB cannot be enabled in staging or production")

        return self


settings = Settings()
