from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_current_state_advances_past_batch19_and_keeps_live_separate() -> None:
    root_state = (ROOT / "00_ETAT_ACTUEL_POST_BATCH_15.md").read_text(encoding="utf-8")
    docs_state = (ROOT / "docs" / "00_ETAT_ACTUEL_POST_BATCH_15.md").read_text(
        encoding="utf-8"
    )

    assert root_state == docs_state
    assert "État actuel post-Batch 22.1" in root_state
    assert "Recruitment reste advisory-only" in root_state
    assert "Task Forces restent temporaires" in root_state
    assert "Master Portfolio Layer" in root_state
    assert "Frontend V2" in root_state
    assert "Le Risk Engine reste l’autorité de risque" in root_state
    assert "Le LIVE n’est jamais déduit d’un backtest ou d’un résultat IA" in root_state


def test_central_changelog_records_batch19_closure() -> None:
    changelog = (ROOT / "CHANGELOG_BATCH.md").read_text(encoding="utf-8")
    assert "BATCH19_CLOSURE_START" in changelog
    assert "Batch 19 — Recruitment Engine — clôture" in changelog
    assert "ADVISORY_READ_ONLY" in changelog
    assert "BATCH19_CLOSURE_END" in changelog
