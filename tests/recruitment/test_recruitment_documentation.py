from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIRRORED_DOCS = (
    "03_SYSTEME_AGENTS.md",
    "06_EVALUATION_ET_APPRENTISSAGE.md",
    "08_API_ET_MODELES_DE_DONNEES.md",
    "09_ROADMAP_DEVELOPPEMENT.md",
    "10_DECISIONS_ET_CHANGELOG.md",
    "11_BACKTESTING_ET_REPLAY_HISTORIQUE.md",
)
DOCS_ONLY = (
    "01_PROJECT_MASTER.md",
    "02_ARCHITECTURE.md",
    "07_SECURITE_ET_OPERATIONS.md",
)


def test_batch19_documentation_layout_matches_repository_contract() -> None:
    for name in MIRRORED_DOCS:
        root = (ROOT / name).read_text(encoding="utf-8")
        mirror = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert root == mirror, name

    for name in DOCS_ONLY:
        assert not (ROOT / name).exists(), f"unexpected root duplicate: {name}"
        assert (ROOT / "docs" / name).is_file(), name


def test_recruitment_contracts_are_documented_without_auto_promotion() -> None:
    agents = (ROOT / "03_SYSTEME_AGENTS.md").read_text(encoding="utf-8")
    evaluation = (ROOT / "06_EVALUATION_ET_APPRENTISSAGE.md").read_text(encoding="utf-8")
    api = (ROOT / "08_API_ET_MODELES_DE_DONNEES.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "09_ROADMAP_DEVELOPPEMENT.md").read_text(encoding="utf-8")

    assert "PROMOTION_RECOMMENDED" in agents
    assert "n'est pas un `AgentRegistryEntry`" in agents
    assert "BASELINE" in evaluation and "WITH_CANDIDATE" in evaluation
    assert "candidate_direct_ai_cost_eur" in evaluation
    assert "marginal_total_ai_cost_eur" in evaluation
    assert "GET /api/recruitment/capabilities" in api
    assert "ADVISORY_READ_ONLY" in api
    assert "mutation automatique d'`AgentRegistry`" in roadmap
    assert "Batch 19 — Recruitment Engine" in roadmap
    assert "Batch 20 — Task Force dynamique" in roadmap
    assert "Batch 21 — Master Portfolio Layer" in roadmap


def test_recruitment_security_and_decision_records_are_explicit() -> None:
    security = (ROOT / "docs" / "07_SECURITE_ET_OPERATIONS.md").read_text(
        encoding="utf-8"
    )
    decisions = (ROOT / "10_DECISIONS_ET_CHANGELOG.md").read_text(encoding="utf-8")
    backtest = (ROOT / "11_BACKTESTING_ET_REPLAY_HISTORIQUE.md").read_text(
        encoding="utf-8"
    )

    assert "audit `STALE`" in security
    assert "ADR-026" in decisions
    assert "advisory-only" in decisions
    assert "HistoricalReplayRunner / PAPER isolé" in backtest
    assert "OOS" in backtest
