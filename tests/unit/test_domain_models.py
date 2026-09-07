import pytest
from pydantic import ValidationError

from app.domain.enums import SystemMode
from app.domain.models import SystemConfig


def test_system_config_normalizes_symbols() -> None:
    config = SystemConfig(
        system_id="balanced_v1",
        mode=SystemMode.PAPER,
        risk_profile_id="balanced",
        ai_budget_id="prototype",
        symbols=("btc", "eth", "sol"),
    )
    assert config.symbols == ("BTC", "ETH", "SOL")


def test_system_config_rejects_duplicate_symbols() -> None:
    with pytest.raises(ValidationError, match="doivent être uniques"):
        SystemConfig(
            system_id="balanced_v1",
            mode=SystemMode.PAPER,
            risk_profile_id="balanced",
            ai_budget_id="prototype",
            symbols=("BTC", "btc"),
        )
