from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PaperBrokerConfig:
    system_id: str = "balanced_v1"
    initial_balance: Decimal = Decimal("100")
    maker_fee_bps: Decimal = Decimal("10")
    taker_fee_bps: Decimal = Decimal("10")
    market_slippage_bps: Decimal = Decimal("5")
    allow_short: bool = True

    def __post_init__(self) -> None:
        if not self.system_id.strip():
            raise ValueError("system_id must not be empty")
        if self.initial_balance <= 0:
            raise ValueError("initial_balance must be > 0")
        for field_name in ("maker_fee_bps", "taker_fee_bps", "market_slippage_bps"):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
