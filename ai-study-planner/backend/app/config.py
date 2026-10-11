"""Application settings, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT = "dev-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./study_planner.db"
    secret_key: str = _INSECURE_DEFAULT
    cors_origins: str = "http://localhost:5173"
    access_token_minutes: int = 60 * 24 * 7

    ai_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"
    ai_provider: str = "anthropic"
    ai_base_url: str = ""
    ai_daily_limit_per_user: int = 25
    ai_cache_hours: int = 24

    max_request_bytes: int = 200_000
    demo_ttl_hours: int = 24

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    def validate_for_runtime(self) -> None:
        if self.is_production and self.secret_key == _INSECURE_DEFAULT:
            raise RuntimeError("SECRET_KEY must be set in production.")
        if self.is_production and len(self.secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters in production.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
