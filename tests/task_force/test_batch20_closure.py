from pathlib import Path

import app.evaluation as evaluation
import app.services.orchestration as orchestration
import app.task_force as task_force


ROOT = Path(__file__).resolve().parents[2]


def test_task_force_runtime_is_public() -> None:
    names = (
        "TaskForceExecutionFailure",
        "TaskForceExecutionFailureStage",
        "TaskForceExecutionRunStatus",
        "TaskForceExecutionUsageSnapshot",
        "TaskForceMemberComputeQuote",
        "TaskForceMemberExecutionRecord",
        "TaskForceMemberUsageSnapshot",
        "TaskForceMultiMemberExecution",
        "TaskForceStructuredGateway",
        "execute_task_force_members",
        "task_force_compute_quote_fingerprint",
        "zero_task_force_execution_usage",
    )
    for name in names:
        assert name in task_force.__all__
        assert hasattr(task_force, name)


def test_task_force_evaluation_and_replay_are_public() -> None:
    names = (
        "TaskForceRunOutcome",
        "TaskForceOutcomeComparison",
        "TaskForceEvaluationReport",
        "compare_task_force_outcomes",
        "evaluate_task_force",
        "TaskForceReplayCampaignReport",
        "TaskForceReplayExecutor",
        "TaskForceReplayPlan",
        "TaskForceReplayAudit",
        "TaskForceReplayAuditStatus",
        "TaskForceReplaySeal",
        "assert_task_force_replay_fresh",
        "audit_task_force_replay",
        "seal_task_force_replay",
    )
    for name in names:
        assert name in evaluation.__all__
        assert hasattr(evaluation, name)


def test_task_force_orchestration_bridges_are_public() -> None:
    names = (
        "TaskForceReportIntegration",
        "prepare_task_force_report_for_orchestration",
        "task_force_report_fingerprint",
        "TaskForceInvocationDecision",
        "TaskForceInvocationPolicy",
        "TaskForceInvocationStatus",
        "TaskForceTriggerSignal",
        "evaluate_task_force_trigger",
        "task_force_invocation_policy_fingerprint",
        "task_force_trigger_signal_fingerprint",
    )
    for name in names:
        assert name in orchestration.__all__
        assert hasattr(orchestration, name)


def test_batch20_documentation_closure_is_present() -> None:
    state = (ROOT / "00_ETAT_ACTUEL_POST_BATCH_15.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "09_ROADMAP_DEVELOPPEMENT.md").read_text(encoding="utf-8")
    decisions = (ROOT / "10_DECISIONS_ET_CHANGELOG.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG_BATCH.md").read_text(encoding="utf-8")

    assert state.startswith("# Money Heist — État actuel post-Batch 20")
    assert "## 23. Batch 20 — Task Force dynamique" in roadmap
    assert "**État : livré et validé.**" in roadmap
    assert "Batch 21 — Master Portfolio Layer" in roadmap
    assert "ADR-027 — Task Force temporaire registry-only" in decisions
    assert "BATCH20_CLOSURE_START" in changelog


def test_documentation_mirrors_remain_identical() -> None:
    names = (
        "00_ETAT_ACTUEL_POST_BATCH_15.md",
        "03_SYSTEME_AGENTS.md",
        "06_EVALUATION_ET_APPRENTISSAGE.md",
        "08_API_ET_MODELES_DE_DONNEES.md",
        "09_ROADMAP_DEVELOPPEMENT.md",
        "10_DECISIONS_ET_CHANGELOG.md",
        "11_BACKTESTING_ET_REPLAY_HISTORIQUE.md",
    )
    for name in names:
        root_text = (ROOT / name).read_text(encoding="utf-8")
        docs_text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert root_text == docs_text


def test_docs_only_layout_is_preserved() -> None:
    for name in (
        "01_PROJECT_MASTER.md",
        "02_ARCHITECTURE.md",
        "07_SECURITE_ET_OPERATIONS.md",
    ):
        assert not (ROOT / name).exists()
        assert (ROOT / "docs" / name).exists()
