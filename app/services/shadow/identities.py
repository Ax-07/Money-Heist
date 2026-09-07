from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ShadowSystemFamily(StrEnum):
    CONSERVATIVE = "CONSERVATIVE"
    BALANCED = "BALANCED"
    AGGRESSIVE = "AGGRESSIVE"


@dataclass(frozen=True, slots=True)
class ShadowSystemIdentity:
    """Stable identity for one PAPER-only SHADOW twin.

    The identity deliberately contains no numerical risk limit. Risk limits are
    injected separately through ``RiskProfile`` and may remain unresolved.
    """

    system_id: str
    family: ShadowSystemFamily
    display_name: str
    aliases: tuple[str, ...]
    execution_order: int
    mode: str = "SHADOW"

    def __post_init__(self) -> None:
        if not self.system_id.strip():
            raise ValueError("system_id must not be empty")
        if self.execution_order < 0:
            raise ValueError("execution_order must be >= 0")
        if self.mode != "SHADOW":
            raise ValueError("Batch 11 identities are SHADOW-only")


CONSERVATIVE_VAULT = ShadowSystemIdentity(
    system_id="shadow_conservative_vault_v1",
    family=ShadowSystemFamily.CONSERVATIVE,
    display_name="Conservative",
    aliases=("Vault",),
    execution_order=10,
)

BALANCED = ShadowSystemIdentity(
    system_id="shadow_balanced_v1",
    family=ShadowSystemFamily.BALANCED,
    display_name="Balanced",
    aliases=(),
    execution_order=20,
)

AGGRESSIVE_TOKYO = ShadowSystemIdentity(
    system_id="shadow_aggressive_tokyo_v1",
    family=ShadowSystemFamily.AGGRESSIVE,
    display_name="Aggressive",
    aliases=("Tokyo",),
    execution_order=30,
)

DEFAULT_SHADOW_SYSTEMS: tuple[ShadowSystemIdentity, ...] = (
    CONSERVATIVE_VAULT,
    BALANCED,
    AGGRESSIVE_TOKYO,
)


def default_shadow_systems() -> tuple[ShadowSystemIdentity, ...]:
    """Return the three Batch 11 identities in deterministic execution order."""

    return DEFAULT_SHADOW_SYSTEMS
