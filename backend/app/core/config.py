"""Application settings loaded from environment variables (.env).

The validator in ``Settings`` is the FIRST safety layer of Development Mode:
the app refuses to start when the configuration could send real WhatsApp
messages or production conversion events from a non-production environment.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class WhatsAppProviderName(StrEnum):
    SIMULATED = "simulated"
    WHATSAPP_CLOUD = "whatsapp_cloud"


class ConversionProviderName(StrEnum):
    NOOP = "noop"
    META_CAPI = "meta_capi"


class JobQueueMode(StrEnum):
    ARQ = "arq"  # real background worker via Redis
    INLINE = "inline"  # run jobs immediately in-process (tests / quick local runs)


WEAK_SECRET_MARKERS = ("changeme", "your-", "dev-only")
MIN_PRODUCTION_SECRET_LENGTH = 32


class ConfigurationError(RuntimeError):
    """Raised when the configuration is unsafe or inconsistent."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DIPO AI Lead Management"
    app_env: AppEnv = AppEnv.DEVELOPMENT
    log_level: str = "INFO"
    simulator_enabled: bool = True
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- Providers (adapter selection) ---
    whatsapp_provider: WhatsAppProviderName = WhatsAppProviderName.SIMULATED
    ai_provider: str = "mock"
    conversion_provider: ConversionProviderName = ConversionProviderName.NOOP
    job_queue: JobQueueMode = JobQueueMode.ARQ

    # --- Infrastructure ---
    database_url: str = "postgresql+psycopg://dipo:changeme@localhost:5432/dipo_leads"
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth ---
    jwt_secret: str = "dev-only-insecure-jwt-secret-change-me"  # noqa: S105 - placeholder
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 8
    cookie_secure: bool = False

    # --- Meta WhatsApp Cloud API (production only, NEVER commit real values) ---
    whatsapp_api_base_url: str = "https://graph.facebook.com"
    whatsapp_api_version: str = "v21.0"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_webhook_verify_token: str = ""
    # Extra kill switch: even in production nothing is sent until this is true.
    whatsapp_cloud_send_enabled: bool = False

    # --- Dev seed (dummy accounts only) ---
    seed_admin_email: str = "admin@example.com"
    seed_default_password: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.PRODUCTION

    @model_validator(mode="after")
    def enforce_safety_rules(self) -> "Settings":
        errors: list[str] = []

        if self.app_env == AppEnv.DEVELOPMENT:
            if self.whatsapp_provider != WhatsAppProviderName.SIMULATED:
                errors.append(
                    "APP_ENV=development requires WHATSAPP_PROVIDER=simulated "
                    f"(got '{self.whatsapp_provider}')."
                )
            if self.conversion_provider != ConversionProviderName.NOOP:
                errors.append(
                    "APP_ENV=development requires CONVERSION_PROVIDER=noop "
                    f"(got '{self.conversion_provider}')."
                )
            if self.whatsapp_cloud_send_enabled:
                errors.append("APP_ENV=development requires WHATSAPP_CLOUD_SEND_ENABLED=false.")

        if self.app_env == AppEnv.PRODUCTION:
            if self.simulator_enabled:
                errors.append("APP_ENV=production requires SIMULATOR_ENABLED=false.")
            secret = self.jwt_secret.lower()
            if len(self.jwt_secret) < MIN_PRODUCTION_SECRET_LENGTH or any(
                marker in secret for marker in WEAK_SECRET_MARKERS
            ):
                errors.append(
                    "APP_ENV=production requires a strong JWT_SECRET "
                    f"(at least {MIN_PRODUCTION_SECRET_LENGTH} random characters)."
                )
            if self.whatsapp_provider == WhatsAppProviderName.WHATSAPP_CLOUD:
                missing = [
                    name
                    for name in (
                        "whatsapp_access_token",
                        "whatsapp_phone_number_id",
                        "whatsapp_app_secret",
                        "whatsapp_webhook_verify_token",
                    )
                    if not getattr(self, name)
                ]
                if missing:
                    errors.append(
                        "WHATSAPP_PROVIDER=whatsapp_cloud requires: "
                        + ", ".join(m.upper() for m in missing)
                        + "."
                    )

        if errors:
            raise ConfigurationError("Unsafe configuration: " + " ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
