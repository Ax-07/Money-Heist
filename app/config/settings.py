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

    # Batch 15 — configuration d'éligibilité uniquement.
    # Aucune de ces valeurs n'arme le LIVE et aucune variable d'environnement
    # n'est transformée en autorisation opérateur.
    live_environment: Literal["disabled", "kraken_spot_eur"] = "disabled"
    live_system_id: str | None = Field(default=None, min_length=1, max_length=100)
    live_risk_profile_file: str | None = None
    live_market_max_age_seconds: float | None = Field(default=None, gt=0)
    live_metadata_max_age_seconds: float | None = Field(default=None, gt=0)
    live_timeframes: str | None = None

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("sqlite:///"):
            raise ValueError("Batch 01 supporte uniquement une base SQLite locale.")
        return value

    @field_validator("live_system_id", "live_risk_profile_file", "live_timeframes", mode="before")
    @classmethod
    def empty_live_values_are_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def gate_live_configuration(self) -> "Settings":
        if self.runtime_mode is not SystemMode.LIVE:
            return self

        # Preserve the historical fail-closed behaviour for a plain
        # runtime_mode=LIVE. Batch 15 only makes LIVE *configurable* when an
        # independent production environment and target system are explicit.
        # Submission still requires the ephemeral operator arm + preflight.
        if (
            self.app_env != "production"
            or self.live_environment != "kraken_spot_eur"
            or self.live_system_id is None
        ):
            raise ValueError(
                "Le mode LIVE est désactivé tant que Batch 15 n'a pas une "
                "configuration production explicite (live_environment=kraken_spot_eur "
                "et live_system_id)."
            )
        return self

    @property
    def live_timeframe_values(self) -> tuple[str, ...] | None:
        if self.live_timeframes is None:
            return None
        values = tuple(part.strip() for part in self.live_timeframes.split(",") if part.strip())
        return values or None

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
