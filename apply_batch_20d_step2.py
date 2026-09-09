from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
CORE = ROOT / "app" / "agents" / "core.py"
PIPELINE = ROOT / "app" / "services" / "orchestration" / "pipeline.py"


CORE_SIGNATURE_OLD = '''    async def finalize_with_schema(\n        self,\n        *,\n        system_id: str,\n        opportunity: dict[str, Any],\n        market_context: dict[str, Any],\n        specialist_analyses: list[dict[str, Any]],\n        palermo_review: dict[str, Any],\n        output_model: type[T],\n        opportunity_id: UUID | None = None,\n    ) -> AIGatewayResult[T]:\n'''
CORE_SIGNATURE_NEW = '''    async def finalize_with_schema(\n        self,\n        *,\n        system_id: str,\n        opportunity: dict[str, Any],\n        market_context: dict[str, Any],\n        specialist_analyses: list[dict[str, Any]],\n        palermo_review: dict[str, Any],\n        output_model: type[T],\n        task_force_report: dict[str, Any] | None = None,\n        opportunity_id: UUID | None = None,\n    ) -> AIGatewayResult[T]:\n'''

CORE_BODY_OLD = '''        return await self._run(\n            system_id=system_id,\n            payload={\n                "opportunity": opportunity,\n                "market_context": market_context,\n                "specialist_analyses": specialist_analyses,\n                "palermo_review": palermo_review,\n            },\n            output_model=output_model,\n            opportunity_id=opportunity_id,\n            phase="finalize",\n        )\n'''
CORE_BODY_NEW = '''        payload = {\n            "opportunity": opportunity,\n            "market_context": market_context,\n            "specialist_analyses": specialist_analyses,\n            "palermo_review": palermo_review,\n        }\n        if task_force_report is not None:\n            payload["task_force_report"] = task_force_report\n\n        return await self._run(\n            system_id=system_id,\n            payload=payload,\n            output_model=output_model,\n            opportunity_id=opportunity_id,\n            phase="finalize",\n        )\n'''

CORE_FINALIZE_SIGNATURE_OLD = '''    async def finalize(\n        self,\n        *,\n        system_id: str,\n        opportunity: dict[str, Any],\n        market_context: dict[str, Any],\n        specialist_analyses: list[dict[str, Any]],\n        palermo_review: dict[str, Any],\n        opportunity_id: UUID | None = None,\n    ) -> AIGatewayResult[ProfessorDecision]:\n'''
CORE_FINALIZE_SIGNATURE_NEW = '''    async def finalize(\n        self,\n        *,\n        system_id: str,\n        opportunity: dict[str, Any],\n        market_context: dict[str, Any],\n        specialist_analyses: list[dict[str, Any]],\n        palermo_review: dict[str, Any],\n        task_force_report: dict[str, Any] | None = None,\n        opportunity_id: UUID | None = None,\n    ) -> AIGatewayResult[ProfessorDecision]:\n'''

CORE_FINALIZE_CALL_OLD = '''            specialist_analyses=specialist_analyses,\n            palermo_review=palermo_review,\n            output_model=ProfessorDecision,\n            opportunity_id=opportunity_id,\n'''
CORE_FINALIZE_CALL_NEW = '''            specialist_analyses=specialist_analyses,\n            palermo_review=palermo_review,\n            output_model=ProfessorDecision,\n            task_force_report=task_force_report,\n            opportunity_id=opportunity_id,\n'''

PIPELINE_IMPORT_OLD = '''from app.market.features.models import FeatureSnapshot\nfrom app.market.scanner.models import CandidateOpportunity\n\nfrom .compute_gate import ComputeGate\n'''
PIPELINE_IMPORT_NEW = '''from app.market.features.models import FeatureSnapshot\nfrom app.market.scanner.models import CandidateOpportunity\nfrom app.task_force.aggregation import TaskForceReport\n\nfrom .compute_gate import ComputeGate\n'''

PIPELINE_BRIDGE_IMPORT_OLD = '''from .specialist_contexts import SpecialistContextProvider\n'''
PIPELINE_BRIDGE_IMPORT_NEW = '''from .specialist_contexts import SpecialistContextProvider\nfrom .task_force_report import prepare_task_force_report_for_orchestration\n'''

PIPELINE_GROUNDING_OLD = '''def _assert_grounded_final_evidence(\n    evidence: list[EvidenceReference],\n    *,\n    opportunity: dict[str, Any],\n    market_context: dict[str, Any],\n    specialist_analyses: list[dict[str, Any]],\n    palermo_review: dict[str, Any],\n) -> None:\n    available = _leaf_paths(\n        {\n            "opportunity": opportunity,\n            "market_context": market_context,\n            "specialist_analyses": specialist_analyses,\n            "palermo_review": palermo_review,\n        }\n    )\n'''
PIPELINE_GROUNDING_NEW = '''def _assert_grounded_final_evidence(\n    evidence: list[EvidenceReference],\n    *,\n    opportunity: dict[str, Any],\n    market_context: dict[str, Any],\n    specialist_analyses: list[dict[str, Any]],\n    palermo_review: dict[str, Any],\n    task_force_report: dict[str, Any] | None = None,\n) -> None:\n    grounded_inputs = {\n        "opportunity": opportunity,\n        "market_context": market_context,\n        "specialist_analyses": specialist_analyses,\n        "palermo_review": palermo_review,\n    }\n    if task_force_report is not None:\n        grounded_inputs["task_force_report"] = task_force_report\n    available = _leaf_paths(grounded_inputs)\n'''

PIPELINE_RUN_SIGNATURE_OLD = '''        market_context: FeatureSnapshot,\n        now: datetime | None = None,\n        specialist_contexts: Mapping[str, Any] | None = None,\n    ) -> OrchestrationResult:\n'''
PIPELINE_RUN_SIGNATURE_NEW = '''        market_context: FeatureSnapshot,\n        now: datetime | None = None,\n        specialist_contexts: Mapping[str, Any] | None = None,\n        task_force_report: TaskForceReport | None = None,\n    ) -> OrchestrationResult:\n'''

PIPELINE_CONTEXT_ANCHOR_OLD = '''        event(\n            "context",\n            "COMPLETED",\n            opportunity_id=opportunity.opportunity_id,\n            snapshot_id=market_context.snapshot_id,\n            feature_version=market_context.feature_version,\n            scanner_version=opportunity.scanner_version,\n        )\n\n        gate_decision = self.compute_gate.evaluate(opportunity, now=now)\n'''
PIPELINE_CONTEXT_ANCHOR_NEW = '''        event(\n            "context",\n            "COMPLETED",\n            opportunity_id=opportunity.opportunity_id,\n            snapshot_id=market_context.snapshot_id,\n            feature_version=market_context.feature_version,\n            scanner_version=opportunity.scanner_version,\n        )\n\n        task_force_payload = None\n        if task_force_report is not None:\n            try:\n                integration = prepare_task_force_report_for_orchestration(\n                    task_force_report,\n                    opportunity=opportunity,\n                    market_context=market_context,\n                    now=now,\n                )\n            except (ValueError, PermissionError) as exc:\n                event("task_force_report", "FAILED", reason=str(exc))\n                return self._failed(\n                    opportunity=opportunity,\n                    gate_decision=None,\n                    professor_plan=None,\n                    specialist_runs=(),\n                    palermo_run=None,\n                    final_decision=None,\n                    code=PipelineFailureCode.INVALID_CONTEXT,\n                    stage="task_force_report",\n                    message=str(exc),\n                    agent_id=None,\n                    calls=calls,\n                    events=events,\n                )\n            task_force_payload = integration.payload\n            event(\n                "task_force_report",\n                "COMPLETED",\n                task_force_id=integration.task_force_id,\n                execution_run_id=integration.execution_run_id,\n                report_fingerprint_sha256=integration.report_fingerprint_sha256,\n            )\n\n        gate_decision = self.compute_gate.evaluate(opportunity, now=now)\n'''

PIPELINE_FINALIZE_CALL_OLD = '''                specialist_analyses=specialist_payloads,\n                palermo_review=palermo_run.review.model_dump(mode="json"),\n                output_model=ProfessorFinalDecision,\n                opportunity_id=opportunity_uuid,\n'''
PIPELINE_FINALIZE_CALL_NEW = '''                specialist_analyses=specialist_payloads,\n                palermo_review=palermo_run.review.model_dump(mode="json"),\n                output_model=ProfessorFinalDecision,\n                task_force_report=task_force_payload,\n                opportunity_id=opportunity_uuid,\n'''

PIPELINE_GROUNDING_CALL_OLD = '''                specialist_analyses=specialist_payloads,\n                palermo_review=palermo_run.review.model_dump(mode="json"),\n            )\n'''
PIPELINE_GROUNDING_CALL_NEW = '''                specialist_analyses=specialist_payloads,\n                palermo_review=palermo_run.review.model_dump(mode="json"),\n                task_force_report=task_force_payload,\n            )\n'''


def _read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return text, newline


def _write(path: Path, text: str, newline: str) -> None:
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def _patch_core(text: str) -> str:
    if 'task_force_report: dict[str, Any] | None = None' in text:
        return text
    text = _replace_once(text, CORE_SIGNATURE_OLD, CORE_SIGNATURE_NEW, label="core signature")
    text = _replace_once(text, CORE_BODY_OLD, CORE_BODY_NEW, label="core finalize body")
    text = _replace_once(
        text,
        CORE_FINALIZE_SIGNATURE_OLD,
        CORE_FINALIZE_SIGNATURE_NEW,
        label="core public finalize signature",
    )
    return _replace_once(
        text,
        CORE_FINALIZE_CALL_OLD,
        CORE_FINALIZE_CALL_NEW,
        label="core public finalize call",
    )


def _patch_pipeline(text: str) -> str:
    if 'from .task_force_report import prepare_task_force_report_for_orchestration' in text:
        return text
    replacements = (
        (PIPELINE_IMPORT_OLD, PIPELINE_IMPORT_NEW, "pipeline TaskForceReport import"),
        (PIPELINE_BRIDGE_IMPORT_OLD, PIPELINE_BRIDGE_IMPORT_NEW, "pipeline bridge import"),
        (PIPELINE_GROUNDING_OLD, PIPELINE_GROUNDING_NEW, "pipeline grounding"),
        (PIPELINE_RUN_SIGNATURE_OLD, PIPELINE_RUN_SIGNATURE_NEW, "pipeline run signature"),
        (PIPELINE_CONTEXT_ANCHOR_OLD, PIPELINE_CONTEXT_ANCHOR_NEW, "pipeline bridge stage"),
        (PIPELINE_FINALIZE_CALL_OLD, PIPELINE_FINALIZE_CALL_NEW, "pipeline Professor call"),
        (PIPELINE_GROUNDING_CALL_OLD, PIPELINE_GROUNDING_CALL_NEW, "pipeline grounding call"),
    )
    for old, new, label in replacements:
        text = _replace_once(text, old, new, label=label)
    return text


def main() -> None:
    if not CORE.exists() or not PIPELINE.exists():
        raise SystemExit("Run this script from the Money-Heist repository root")

    core_text, core_newline = _read(CORE)
    pipeline_text, pipeline_newline = _read(PIPELINE)

    patched_core = _patch_core(core_text)
    patched_pipeline = _patch_pipeline(pipeline_text)

    # All anchor checks complete before either tracked file is written.
    if patched_core != core_text:
        _write(CORE, patched_core, core_newline)
    if patched_pipeline != pipeline_text:
        _write(PIPELINE, patched_pipeline, pipeline_newline)

    print("Batch 20d Step 2 applied:")
    print("- app/agents/core.py")
    print("- app/services/orchestration/pipeline.py")
    print("- app/services/orchestration/task_force_report.py (from overlay)")


if __name__ == "__main__":
    main()
