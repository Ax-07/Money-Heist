from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.enums import LogLevel, SystemMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MONEY_HEIST_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Money Heist", min_length=1, max_length=100)
    app_version: str = Field(default="0.1.0", min_length=1, max_length=50)
    app_env: Literal["development", "test", "production"] = "development"
    runtime_mode: SystemMode = SystemMode.PAPER
    log_level: LogLevel = LogLevel.INFO
    database_url: str = "sqlite:///./data/money_heist.db"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    default_system_id: str = Field(default="balanced_v1", min_length=1, max_length=100)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("sqlite:///"):
            raise ValueError("Batch 01 supporte uniquement une base SQLite locale.")
        return value

    @model_validator(mode="after")
    def forbid_live_mode_in_foundation(self) -> "Settings":
        if self.runtime_mode is SystemMode.LIVE:
            raise ValueError(
                "Le mode LIVE est désactivé dans Batch 01. "
                "PAPER/SHADOW doivent être validés avant toute activation LIVE."
            )
        return self

    @property
    def sqlite_path(self) -> Path | None:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        raw_path = self.database_url.removeprefix(prefix)
        if raw_path == ":memory:":
            return None
        return Path(raw_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
