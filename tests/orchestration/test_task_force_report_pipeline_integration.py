from __future__ import annotations

import asyncio
import inspect
import json

import pytest

from app.agents.core import TheProfessor
from app.agents.models import EvidenceReference, ProfessorDecision
from app.agents.specialists import UngroundedEvidenceError
from app.services.orchestration.pipeline import (
    OrchestrationPipeline,
    _assert_grounded_final_evidence,
)


class CapturingGateway:
    def __init__(self) -> None:
        self.requests = []

    async def generate_structured(self, request, output_model):
        self.requests.append((request, output_model))
        return None


def test_pipeline_run_exposes_optional_task_force_report_parameter():
    parameters = inspect.signature(OrchestrationPipeline.run).parameters
    assert "task_force_report" in parameters


def test_grounding_accepts_exact_task_force_report_leaf_path():
    evidence = [
        EvidenceReference(
            source_key="task_force_report.findings.0.summary",
            observation="Task Force finding is available to the Professor.",
        )
    ]
    _assert_grounded_final_evidence(
        evidence,
        opportunity={},
        market_context={},
        specialist_analyses=[],
        palermo_review={},
        task_force_report={"findings": [{"summary": "Conditional breakout evidence"}]},
    )


def test_grounding_rejects_task_force_path_when_report_is_absent():
    evidence = [
        EvidenceReference(
            source_key="task_force_report.findings.0.summary",
            observation="Unavailable report must fail grounding.",
        )
    ]
    with pytest.raises(UngroundedEvidenceError):
        _assert_grounded_final_evidence(
            evidence,
            opportunity={},
            market_context={},
            specialist_analyses=[],
            palermo_review={},
            task_force_report=None,
        )


def test_professor_finalize_includes_task_force_report_only_when_supplied():
    gateway = CapturingGateway()
    professor = TheProfessor(gateway)

    asyncio.run(
        professor.finalize_with_schema(
            system_id="balanced_v1",
            opportunity={"opportunity_id": "opp-1"},
            market_context={"snapshot_id": "snapshot-1"},
            specialist_analyses=[],
            palermo_review={"verdict": "CLEAR"},
            output_model=ProfessorDecision,
            task_force_report={"report_fingerprint_sha256": "a" * 64},
        )
    )
    payload = json.loads(gateway.requests[-1][0].input_text)
    assert payload["task_force_report"]["report_fingerprint_sha256"] == "a" * 64

    asyncio.run(
        professor.finalize_with_schema(
            system_id="balanced_v1",
            opportunity={"opportunity_id": "opp-1"},
            market_context={"snapshot_id": "snapshot-1"},
            specialist_analyses=[],
            palermo_review={"verdict": "CLEAR"},
            output_model=ProfessorDecision,
        )
    )
    payload_without_report = json.loads(gateway.requests[-1][0].input_text)
    assert "task_force_report" not in payload_without_report
