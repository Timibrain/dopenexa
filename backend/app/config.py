from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://dopenexa:dopenexa@localhost:5432/dopenexa"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-change-me"
    payment_webhook_secret: str = "dev-only-change-me"
    payment_provider: str = "pending"
    paystack_secret_key: str = ""
    paystack_base_url: str = "https://api.paystack.co"
    access_token_minutes: int = 30
    refresh_token_days: int = 30
    ai_provider: str = "deterministic"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_embedding_model: str = "text-embedding-3-small"
    ai_chat_model: str = "gpt-4o-mini"
    storage_backend: str = "local"
    upload_dir: str = "uploads"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"
    trusted_hosts: str = "*"
    logging_level: str = "INFO"
    debug: bool = False
    error_reporting_dsn: str = ""
    rate_limit_enabled: bool = False
    rate_limit_per_minute: int = 60
    object_storage_bucket: str = ""
    object_storage_endpoint: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    apns_enabled: bool = False
    apns_team_id: str = ""
    apns_key_id: str = ""
    apns_bundle_id: str = ""
    apns_private_key: str = ""
    minimum_payout_ngn: int = 1000
    payment_reconciliation_after_minutes: int = 30
    payout_reconciliation_after_minutes: int = 30
    refund_reconciliation_after_minutes: int = 30
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_asyncpg_url(cls, value):
        if isinstance(value, str) and value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value[len("postgresql://"):]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_environment(self):
        env = self.environment.lower()
        if env not in {"development", "staging", "production"}:
            raise ValueError("ENVIRONMENT must be development, staging, or production")
        if env in {"staging", "production"}:
            insecure = {"dev-only-change-me", "dev-only-change-me", "change-me-in-development"}
            if not self.jwt_secret or self.jwt_secret in insecure:
                raise ValueError("JWT_SECRET is required outside development")
            if not self.database_url or "dopenexa:dopenexa@" in self.database_url:
                raise ValueError("DATABASE_URL must be explicitly configured outside development")
            if not self.redis_url or self.redis_url == "redis://localhost:6379/0":
                raise ValueError("REDIS_URL must be explicitly configured outside development")
            if not self.cors_origin_list or "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS must explicitly list approved domains outside development")
            if not self.trusted_host_list or "*" in self.trusted_host_list:
                raise ValueError("TRUSTED_HOSTS must explicitly list approved hosts outside development")
            if self.storage_backend == "local":
                raise ValueError("STORAGE_BACKEND must use external object storage outside development")
            if self.payment_provider.lower() == "paystack" and not self.paystack_secret_key:
                raise ValueError("PAYSTACK_SECRET_KEY is required when Paystack is enabled")
            if self.apns_enabled and not all((self.apns_team_id, self.apns_key_id, self.apns_bundle_id, self.apns_private_key)):
                raise ValueError("APNs configuration is incomplete")
        return self

settings = Settings()
