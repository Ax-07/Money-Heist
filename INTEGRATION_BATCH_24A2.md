# Integration — Batch 24A.2

Baseline required: `0c4549663bf43418ff2d337c63343112f314dceb`.

1. From repository root, verify `git rev-parse HEAD`.
2. Copy the overlay contents into the Money Heist checkout, preserving paths.
3. Run `uv sync`.
4. Run `uv run pytest tests/analytics/indicators -q`.
5. Run `uv run pytest tests/analytics -q`.
6. Run `uv run pytest -q`.
7. Validate only Batch 24A.2 Python paths:
   - `uv run ruff check app/analytics/indicators tests/analytics/indicators apply_batch_24a2_docs.py`
   - `uv run ruff format --check app/analytics/indicators tests/analytics/indicators apply_batch_24a2_docs.py`
   - `git diff --check`
8. Run `uv run python apply_batch_24a2_docs.py` to append the consolidated documentation notes.
9. Inspect `git status --short`, `git diff --stat`, and `git diff`.
10. Do not push until the batch is reviewed and explicitly approved.

The overlay deliberately contains no files under `app/market/features`, scanner, decision
context, agents, orchestration, risk, paper, or live trading paths.
