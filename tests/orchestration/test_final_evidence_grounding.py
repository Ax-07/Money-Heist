from __future__ import annotations

import pytest

from app.agents.models import EvidenceReference
from app.agents.specialists import UngroundedEvidenceError
from app.services.orchestration.pipeline import _assert_grounded_final_evidence


def _evidence(source_key: str) -> list[EvidenceReference]:
    return [EvidenceReference(source_key=source_key, observation="grounded observation")]


def _inputs():
    return {
        "opportunity": {"opportunity_id": "opp-1"},
        "market_context": {"close": 100.0},
        "specialist_analyses": [
            {
                "agent": "berlin",
                "stance": "NEUTRAL",
                "regime": "RANGE",
            },
            {
                "agent": "tokyo",
                "stance": "NEUTRAL",
                "breakout_quality": "UNCONFIRMED",
            },
        ],
        "palermo_review": {
            "verdict": "CAUTION",
            "critical_objections": ["false breakout remains possible"],
            "missing_checks": ["retest confirmation"],
        },
    }


def test_final_grounding_accepts_real_container_path() -> None:
    values = _inputs()
    _assert_grounded_final_evidence(
        _evidence("palermo_review.critical_objections"),
        **values,
    )


def test_final_grounding_accepts_unambiguous_specialist_alias() -> None:
    values = _inputs()
    _assert_grounded_final_evidence(
        _evidence("tokyo.breakout_quality"),
        **values,
    )


def test_final_grounding_keeps_indexed_transport_path_valid() -> None:
    values = _inputs()
    _assert_grounded_final_evidence(
        _evidence("specialist_analyses.1.breakout_quality"),
        **values,
    )


@pytest.mark.parametrize(
    "source_key",
    [
        "tokyo.nonexistent_field",
        "rio.breakout_quality",
        "palermo_review.nonexistent_field",
    ],
)
def test_final_grounding_still_rejects_missing_paths(source_key: str) -> None:
    values = _inputs()
    with pytest.raises(UngroundedEvidenceError, match="unavailable input fields"):
        _assert_grounded_final_evidence(
            _evidence(source_key),
            **values,
        )


def test_duplicate_specialist_agent_alias_fails_closed() -> None:
    values = _inputs()
    values["specialist_analyses"].append(
        {
            "agent": "tokyo",
            "stance": "NEUTRAL",
            "breakout_quality": "CONFIRMED",
        }
    )
    with pytest.raises(UngroundedEvidenceError, match="tokyo.breakout_quality"):
        _assert_grounded_final_evidence(
            _evidence("tokyo.breakout_quality"),
            **values,
        )


def test_final_grounding_accepts_numeric_bracket_index_notation() -> None:
    values = _inputs()
    _assert_grounded_final_evidence(
        _evidence("specialist_analyses[1].breakout_quality"),
        **values,
    )


@pytest.mark.parametrize(
    "source_key",
    [
        "specialist_analyses[9].breakout_quality",
        "specialist_analyses[tokyo].breakout_quality",
        "specialist_analyses[-1].breakout_quality",
    ],
)
def test_final_grounding_rejects_invalid_or_missing_bracket_paths(source_key: str) -> None:
    values = _inputs()
    with pytest.raises(UngroundedEvidenceError, match="unavailable input fields"):
        _assert_grounded_final_evidence(
            _evidence(source_key),
            **values,
        )

