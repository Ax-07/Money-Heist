import pytest
from pydantic import ValidationError

from app.config.settings import Settings
from app.domain.enums import SystemMode


def test_plain_live_mode_remains_rejected():
    with pytest.raises(ValidationError, match="LIVE est désactivé"):
        Settings(runtime_mode="LIVE", _env_file=None)


def test_live_configuration_only_becomes_eligible_with_independent_production_fields():
    settings = Settings(
        app_env="production",
        runtime_mode="LIVE",
        live_environment="kraken_spot_eur",
        live_system_id="balanced_v1",
        _env_file=None,
    )
    assert settings.runtime_mode is SystemMode.LIVE
    assert settings.live_system_id == "balanced_v1"


def test_credentials_are_not_a_settings_authorization_switch(monkeypatch):
    monkeypatch.setenv("MONEY_HEIST_KRAKEN_API_KEY", "fake-key")
    monkeypatch.setenv("MONEY_HEIST_KRAKEN_API_SECRET", "ZmFrZS1zZWNyZXQ=")
    settings = Settings(_env_file=None)
    assert settings.runtime_mode is SystemMode.PAPER
    assert settings.live_environment == "disabled"
