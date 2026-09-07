from __future__ import annotations

import csv
import json
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from io import StringIO
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .models import AgentMetrics, EvaluationReport


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, MappingProxyType):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def report_to_dict(report: EvaluationReport) -> dict[str, Any]:
    return _jsonable(report)


def report_to_json(report: EvaluationReport, *, indent: int = 2) -> str:
    return json.dumps(report_to_dict(report), indent=indent, sort_keys=True, ensure_ascii=False)


def agent_metrics_to_csv(metrics: Iterable[AgentMetrics]) -> str:
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "agent_id",
            "call_count",
            "attempt_count",
            "total_cost_eur",
            "average_cost_eur",
            "average_latency_ms",
            "participation_frequency",
            "disagreement_frequency",
            "average_confidence",
            "prompt_versions",
            "route_ids",
            "model_ids",
        ]
    )
    for item in metrics:
        writer.writerow(
            [
                item.agent_id,
                item.call_count,
                item.attempt_count,
                item.total_cost_eur,
                item.average_cost_eur.value,
                item.average_latency_ms.value,
                item.participation_frequency.value,
                item.disagreement_frequency.value,
                item.average_confidence.value,
                "|".join(item.prompt_versions),
                "|".join(item.route_ids),
                "|".join(item.model_ids),
            ]
        )
    return stream.getvalue()
