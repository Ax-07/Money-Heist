# Batch 16.21e — Agent Context Parity

## Objective

Propagate the exact frozen `DecisionContextV1` from Historical Replay through
PAPER orchestration and into the AI requests used by Professor PLAN, Berlin,
Tokyo, Nairobi, Palermo and Professor FINALIZE.

No Scanner, Risk Engine, broker, position-sizing or prompt logic is changed.

## Compatibility strategy

The existing `FeatureSnapshot` on the primary `1h` timeframe remains the typed
`market_context` at service boundaries.

When a `DecisionContextV1` is available, orchestration serializes it once and
adds it under `market_context.decision_context`.

Existing flat `market_context` fields and evidence paths remain valid. New MTF
evidence can use paths such as:

`market_context.decision_context.market.snapshots.4h.regime`

Calls with no DecisionContext remain unchanged.

## Frozen parity invariant

Before any AI call, orchestration verifies DecisionContext parity for system,
symbol, primary timeframe, decision timestamp, primary snapshot id and Feature
Engine version. Any mismatch fails closed as `INVALID_CONTEXT`.

All agent requests record the same `decision_context_id`,
`decision_context_fingerprint` and binding version in audit metadata.

## Prompt versions

Prompt text is unchanged. Existing specialist prompts already authorize supplied
`market_context`, and Berlin explicitly permits multi-timeframe coherence when
those inputs exist.

## Reproducibility

Binding version:

`decision-context-agent-binding-v1`

MTF replay execution assumptions additionally bind:

`agent_context_binding_version=decision-context-agent-binding-v1`

## Validation

```powershell
uv run pytest -q tests/services/decision_context/test_decision_context_models.py
uv run pytest -q tests/orchestration/test_pipeline.py
uv run pytest -q tests/paper_pipeline/test_pipeline.py
uv run pytest -q tests/backtest/test_replay_runner_mtf.py
uv run pytest -q

uv run python .\scripts\validate_agent_context_parity.py `
  ".\data\historical\binance_spot\backtest_ready\binance_btc_usdc_1m_2025-09-11_2026-09-10.csv"
```
