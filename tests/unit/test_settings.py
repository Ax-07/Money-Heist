import pytest
from pydantic import ValidationError

from app.config.settings import Settings
from app.domain.enums import SystemMode


def test_default_runtime_mode_is_paper() -> None:
    settings = Settings(_env_file=None)
    assert settings.runtime_mode is SystemMode.PAPER


def test_live_mode_is_rejected_in_batch_01() -> None:
    with pytest.raises(ValidationError, match="LIVE est désactivé"):
        Settings(runtime_mode="LIVE", _env_file=None)


def test_non_sqlite_database_is_rejected() -> None:
    with pytest.raises(ValidationError, match="uniquement une base SQLite"):
        Settings(database_url="postgresql://localhost/money_heist", _env_file=None)


def test_invalid_port_fails_cleanly() -> None:
    with pytest.raises(ValidationError):
        Settings(api_port=70000, _env_file=None)
