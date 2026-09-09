from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[2]
_SPEC = spec_from_file_location(
    "apply_batch_18b_step4_closure",
    _ROOT / "apply_batch_18b_step4_closure.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
apply = _MODULE.apply
upsert_marked_block = _MODULE.upsert_marked_block


def test_closure_updater_is_idempotent_and_deletes_migration_tombstone(
    tmp_path: Path,
) -> None:
    files = (
        "06_EVALUATION_ET_APPRENTISSAGE.md",
        "08_API_ET_MODELES_DE_DONNEES.md",
        "09_ROADMAP_DEVELOPPEMENT.md",
        "11_BACKTESTING_ET_REPLAY_HISTORIQUE.md",
        "CHANGELOG_BATCH.md",
    )
    for relative in files:
        path = tmp_path / relative
        path.write_text(f"original:{relative}\n", encoding="utf-8")

    tombstone = tmp_path / "app/evaluation/ablation_campaign_runtime.py"
    tombstone.parent.mkdir(parents=True)
    tombstone.write_text("migration tombstone\n", encoding="utf-8")

    first_changed = apply(tmp_path)
    first = {name: (tmp_path / name).read_text(encoding="utf-8") for name in files}
    second_changed = apply(tmp_path)
    second = {name: (tmp_path / name).read_text(encoding="utf-8") for name in files}

    assert first == second
    assert not tombstone.exists()
    assert "deleted:app/evaluation/ablation_campaign_runtime.py" in first_changed
    assert "deleted:app/evaluation/ablation_campaign_runtime.py" not in second_changed
    assert first["09_ROADMAP_DEVELOPPEMENT.md"].count("BATCH18B_STEP4_ROADMAP_START") == 1
    assert "Batch 19 — Recruitment Engine" in first["09_ROADMAP_DEVELOPPEMENT.md"]


def test_upsert_rejects_unclosed_existing_marker() -> None:
    with pytest.raises(ValueError, match="missing closing marker"):
        upsert_marked_block(
            "<!-- BROKEN_START -->\n",
            "BROKEN",
            "body",
        )
