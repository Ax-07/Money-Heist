from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_batch19_closure_documents_are_present() -> None:
    for name in (
        "README_BATCH_19.md",
        "MANIFEST_BATCH_19.md",
        "CHANGELOG_BATCH_19F.md",
        "INTEGRATION_BATCH_19.md",
    ):
        assert (ROOT / name).is_file(), name


def test_current_state_advances_past_batch19_and_keeps_live_separate() -> None:
    root_state = (ROOT / "00_ETAT_ACTUEL_POST_BATCH_15.md").read_text(encoding="utf-8")
    docs_state = (ROOT / "docs" / "00_ETAT_ACTUEL_POST_BATCH_15.md").read_text(
        encoding="utf-8"
    )
    assert root_state == docs_state
    assert "État actuel post-Batch 20" in root_state
    assert "Batch 20 — Task Force dynamique" in root_state
    assert "Batch 21 — Master Portfolio Layer" in root_state
    assert "candidat Recruitment Batch 19" in root_state
    assert "live_authority = False" in root_state
    assert "L’armement LIVE Batch 15 reste séparé" in root_state


def test_central_changelog_records_batch19_closure() -> None:
    changelog = (ROOT / "CHANGELOG_BATCH.md").read_text(encoding="utf-8")
    assert "BATCH19_CLOSURE_START" in changelog
    assert "Batch 19 — Recruitment Engine — clôture" in changelog
    assert "ADVISORY_READ_ONLY" in changelog
    assert "BATCH19_CLOSURE_END" in changelog


def test_manifest_does_not_version_accidental_root_document_duplicates() -> None:
    manifest = (ROOT / "MANIFEST_BATCH_19.md").read_text(encoding="utf-8")
    assert "docs/01_PROJECT_MASTER.md" in manifest
    assert "docs/02_ARCHITECTURE.md" in manifest
    assert "docs/07_SECURITE_ET_OPERATIONS.md" in manifest
    assert "ne doivent pas être versionnés à la racine" in manifest
