from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://youtube:change-me@db:5432/youtube"
    secret_key: SecretStr = SecretStr("local-development-only-change-this-secret")
    access_token_expire_minutes: int = Field(default=15, gt=0, le=60)
    refresh_token_expire_days: int = Field(default=30, gt=0, le=365)
    refresh_cookie_name: str = "youtube_refresh"

    @model_validator(mode="after")
    def validate_secret_key(self) -> Settings:
        environment = self.app_env.casefold()
        secret = self.secret_key.get_secret_value()
        is_production = environment in {"production", "prod", "staging"}

        if is_production and (len(secret) < 32 or secret.startswith("replace-")):
            raise ValueError("SECRET_KEY must be a unique random value with at least 32 characters")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
