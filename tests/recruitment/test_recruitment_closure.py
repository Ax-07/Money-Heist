from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def test_current_state_advances_past_batch19_and_keeps_live_separate() -> None:
    state = (DOCS / "00_ETAT_ACTUEL_POST_BATCH_15.md").read_text(encoding="utf-8")

    assert state.startswith("# Money Heist — Mémoire projet / état courant")
    assert "**Statut :** contexte de démarrage canonique" in state
    assert "Recruitment Engine advisory-only et opérateur-gaté" in state
    assert "Task Forces temporaires, budgétées et sans autorité LIVE" in state
    assert "Master Portfolio Layer / Master Professor advisory" in state
    assert "Frontend V2" in state
    assert "l’IA propose ; le Risk Engine déterministe autorise" in state
    assert "aucune promotion ne doit être déduite d’un backtest ou d’un rapport de recherche" in state


def test_central_changelog_records_batch19_closure() -> None:
    changelog = (ROOT / "CHANGELOG_BATCH.md").read_text(encoding="utf-8")
    assert "BATCH19_CLOSURE_START" in changelog
    assert "Batch 19 — Recruitment Engine — clôture" in changelog
    assert "ADVISORY_READ_ONLY" in changelog
    assert "BATCH19_CLOSURE_END" in changelog
