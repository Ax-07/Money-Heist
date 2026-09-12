from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from app.services.backtest.denver_prior import (
    DenverPriorPolicy,
    FrozenDenverPriorCatalog,
)
from app.services.backtest.mtf_runtime import MTF_RUNTIME_VERSION
from app.services.backtest.splits import BacktestPeriodRole


DENVER_RUNTIME_VERSION = "frozen-denver-runtime-v1"


class DenverActivationMode(StrEnum):
    OOS_ONLY = "OOS_ONLY"
    ALL_PERIODS = "ALL_PERIODS"


def validate_denver_prior_compatibility(
    prior: FrozenDenverPriorCatalog,
    *,
    system_id: str,
    symbol: str,
    decision_timeframe: str = "1h",
) -> None:
    normalized_system = system_id.strip()
    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = decision_timeframe.strip().lower()
    if not normalized_system:
        raise ValueError("system_id must not be blank")
    if not normalized_symbol:
        raise ValueError("symbol must not be blank")
    if not normalized_timeframe:
        raise ValueError("decision_timeframe must not be blank")

    for observation in prior.catalog.observations:
        setup = observation.setup
        if setup.system_id != normalized_system:
            raise ValueError(
                "Denver prior system_id does not match target system"
            )
        if setup.symbol.strip().upper() != normalized_symbol:
            raise ValueError(
                "Denver prior symbol does not match target dataset"
            )
        if setup.timeframe.strip().lower() != normalized_timeframe:
            raise ValueError(
                "Denver prior setup timeframe does not match decision timeframe"
            )


def denver_prior_execution_assumptions(
    prior: FrozenDenverPriorCatalog,
    *,
    activation_mode: DenverActivationMode | str,
) -> dict[str, str]:
    mode = DenverActivationMode(str(activation_mode))
    if (
        mode is DenverActivationMode.OOS_ONLY
        and prior.policy is not DenverPriorPolicy.STRICT_PRE_OOS
    ):
        raise ValueError(
            "OOS_ONLY Denver activation requires STRICT_PRE_OOS prior"
        )

    assumptions = dict(prior.reproducibility_assumptions)
    assumptions.update(
        {
            "denver_runtime_version": DENVER_RUNTIME_VERSION,
            "denver_activation_mode": mode.value,
            "denver_formal_oos": (
                "true"
                if mode is DenverActivationMode.OOS_ONLY
                else "false"
            ),
        }
    )
    return assumptions


def denver_runner_kwargs(
    assumptions: Mapping[str, str],
    prior: FrozenDenverPriorCatalog | None,
    *,
    role: BacktestPeriodRole | None,
) -> dict[str, object]:
    marker = assumptions.get("denver_runtime_version")
    if marker is None:
        if prior is not None:
            raise ValueError(
                "frozen Denver prior was injected but Denver runtime is not "
                "enabled in execution_assumptions"
            )
        return {}

    if marker != DENVER_RUNTIME_VERSION:
        raise ValueError(
            "Denver runtime assumptions are incoherent: "
            f"denver_runtime_version={marker!r}, "
            f"expected {DENVER_RUNTIME_VERSION!r}"
        )
    if assumptions.get("mtf_runtime_version") != MTF_RUNTIME_VERSION:
        raise ValueError("frozen Denver runtime requires full MTF runtime")
    if prior is None:
        raise ValueError(
            "enabled Denver runtime requires the validated frozen prior"
        )

    raw_mode = assumptions.get("denver_activation_mode")
    try:
        mode = DenverActivationMode(str(raw_mode))
    except ValueError as exc:
        raise ValueError(
            "denver_activation_mode must be OOS_ONLY or ALL_PERIODS"
        ) from exc

    expected = denver_prior_execution_assumptions(
        prior,
        activation_mode=mode,
    )
    for key, value in expected.items():
        actual = assumptions.get(key)
        if actual != value:
            raise ValueError(
                "Denver runtime assumptions are incoherent: "
                f"{key}={actual!r}, expected {value!r}"
            )

    if mode is DenverActivationMode.OOS_ONLY:
        if role is None:
            raise ValueError(
                "OOS_ONLY Denver runtime requires an explicit period role"
            )
        if role is not BacktestPeriodRole.OOS:
            return {}
        return {
            "historical_denver_prior": prior,
            "denver_formal_oos": True,
        }

    return {
        "historical_denver_prior": prior,
        "denver_formal_oos": False,
    }


__all__ = [
    "DENVER_RUNTIME_VERSION",
    "DenverActivationMode",
    "denver_prior_execution_assumptions",
    "denver_runner_kwargs",
    "validate_denver_prior_compatibility",
]
