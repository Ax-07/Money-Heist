from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def test_current_state_advances_past_batch19_and_keeps_live_separate() -> None:
    state = (DOCS / "00_ETAT_ACTUEL_POST_BATCH_15.md").read_text(encoding="utf-8")

    assert "État actuel post-Batch 22.1" in state
    assert "Recruitment reste advisory-only" in state
    assert "Task Forces restent temporaires" in state
    assert "Master Portfolio Layer" in state
    assert "Frontend V2" in state
    assert "Le Risk Engine reste l’autorité de risque" in state
    assert "Le LIVE n’est jamais déduit d’un backtest ou d’un résultat IA" in state


def test_central_changelog_records_batch19_closure() -> None:
    changelog = (ROOT / "CHANGELOG_BATCH.md").read_text(encoding="utf-8")
    assert "BATCH19_CLOSURE_START" in changelog
    assert "Batch 19 — Recruitment Engine — clôture" in changelog
    assert "ADVISORY_READ_ONLY" in changelog
    assert "BATCH19_CLOSURE_END" in changelog
