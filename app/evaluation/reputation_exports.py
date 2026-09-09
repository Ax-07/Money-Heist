from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from .reputation_advisory import AgentReputationAdvisoryReport


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def reputation_advisory_to_dict(
    report: AgentReputationAdvisoryReport,
) -> dict[str, Any]:
    """Return a JSON-safe, deterministic projection of one Batch 18 advisory report."""

    projected = _jsonable(report)
    if not isinstance(projected, dict):  # pragma: no cover - structural guard
        raise TypeError("AgentReputationAdvisoryReport must project to a dict")
    return projected


def reputation_advisory_to_json(
    report: AgentReputationAdvisoryReport,
    *,
    indent: int | None = 2,
) -> str:
    """Serialize one advisory report without changing its audit fingerprint or evidence."""

    return json.dumps(
        reputation_advisory_to_dict(report),
        indent=indent,
        sort_keys=True,
        ensure_ascii=False,
    )
