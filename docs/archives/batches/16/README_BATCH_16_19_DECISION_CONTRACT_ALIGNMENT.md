# Batch 16.19 — Decision Contract Alignment

The LIVE_EVAL smoke is technically clean but revealed a decision-contract mismatch.

Changes:
- preserve professor@v1 and palermo@v1;
- add and activate professor@v2 and palermo@v2;
- pass the current opportunity explicitly to Palermo;
- no look-ahead: future candles/retests/follow-through cannot be assumed or universally required;
- optional missing contexts lower confidence but do not automatically veto unless the thesis depends on them;
- Palermo must not require entry/stop/targets/RR before Professor finalization;
- Professor finalization owns proposed trade parameters, which remain subject to the deterministic Risk Engine;
- NO_TRADE remains valid and no trade is forced.

Validation:
```powershell
uv run pytest -q tests/agents/test_core_agents.py
uv run pytest -q tests/orchestration/test_pipeline.py
uv run pytest -q
```
