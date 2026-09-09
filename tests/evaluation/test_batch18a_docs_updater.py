from __future__ import annotations

from pathlib import Path

from apply_batch_18a_step4_docs import BLOCKS, main, upsert_block


def test_upsert_block_appends_once_and_is_idempotent() -> None:
    block = BLOCKS["06_EVALUATION_ET_APPRENTISSAGE.md"]
    first, changed = upsert_block("# Doc\n", block)
    second, changed_again = upsert_block(first, block)

    assert changed is True
    assert changed_again is False
    assert first == second
    assert first.count("BATCH18A_STEP4_EVALUATION_START") == 1


def test_updater_preserves_existing_local_content(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "08_API_ET_MODELES_DE_DONNEES.md"
    target.write_text("# API\n\nLOCAL STEP 1 CONTENT\n", encoding="utf-8")

    assert main(tmp_path) == 0
    first = target.read_text(encoding="utf-8")
    assert "LOCAL STEP 1 CONTENT" in first
    assert "BATCH18A_STEP4_API_START" in first

    assert main(tmp_path) == 0
    second = target.read_text(encoding="utf-8")
    assert first == second


def test_updater_updates_root_and_docs_copies_when_both_exist(tmp_path: Path) -> None:
    filename = "09_ROADMAP_DEVELOPPEMENT.md"
    (tmp_path / filename).write_text("# Roadmap root\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / filename).write_text("# Roadmap docs\n", encoding="utf-8")

    assert main(tmp_path) == 0

    for path in (tmp_path / filename, tmp_path / "docs" / filename):
        text = path.read_text(encoding="utf-8")
        assert text.count("BATCH18A_STEP4_ROADMAP_START") == 1
