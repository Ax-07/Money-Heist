# Batch 21a — Step 1 — Master Portfolio State Foundation

Baseline: `9900de3 feat(task-force): complete Batch 20 dynamic task force`

This overlay adds only read-only Master Portfolio state contracts and a deterministic snapshot builder.

It intentionally does **not** add allocation, reservation, Master Risk, broker integration, AI, LIVE,
Reputation, Recruitment, Task Force mutation, or pipeline hooks.

## Files

- `app/portfolio/__init__.py`
- `app/portfolio/models.py`
- `app/portfolio/snapshot.py`
- `tests/portfolio/test_master_snapshot.py`

## Targeted validation

```powershell
uv run pytest -q tests/portfolio/test_master_snapshot.py
uv run ruff check app/portfolio tests/portfolio/test_master_snapshot.py
uv run pytest -q

git status --short
```
