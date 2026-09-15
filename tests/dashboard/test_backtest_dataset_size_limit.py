from __future__ import annotations

import pytest

from app.dashboard.backtest import DatasetInput, dataset_csv_max_bytes


def test_dataset_limit_defaults_to_256_mib(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONEY_HEIST_DATASET_UPLOAD_MAX_MB", raising=False)
    assert dataset_csv_max_bytes() == 256 * 1024 * 1024


def test_dataset_limit_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONEY_HEIST_DATASET_UPLOAD_MAX_MB", "0")
    assert dataset_csv_max_bytes() is None


def test_dataset_input_uses_configured_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONEY_HEIST_DATASET_UPLOAD_MAX_MB", "1")
    with pytest.raises(ValueError, match="configured dataset limit"):
        DatasetInput(csv_text="x" * (1024 * 1024 + 1), symbol="BTC/USDC", timeframe="1m")
