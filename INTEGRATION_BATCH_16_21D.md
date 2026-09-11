# Batch 16.21d — DecisionContext Contract

## Objective

Introduce the immutable context object that will eventually be shared by the
Professor, specialists and Palermo in both Historical Replay and live paths.

This batch defines and freezes the contract. It does **not** change agent prompts
or orchestration inputs yet.

## Contract

`DecisionContextV1` contains:

- `context_id`;
- `context_fingerprint`;
- `schema_version`;
- `context_version`;
- `system_id`;
- `symbol`;
- `as_of`;
- `primary_timeframe`;
- `timeframe_policy_version`;
- `market` = Batch 16.21c `MultiTimeframeFeatureContext`;
- `structure`;
- `derivatives`;
- `statistics`;
- `portfolio_summary`;
- `market_constraints`;
- `microstructure`;
- per-component provenance;
- explicit `missing_components`.

Default contract version:

`decision-context-v1`

## Anti-lookahead

Every available source carries:

- `observed_at`;
- `available_at`;
- source identity;
- quality;
- missing fields;
- optional source fingerprint.

The invariant is strict:

`provenance.available_at <= DecisionContext.as_of`

Any source whose `available_at` is later than the decision time is rejected.

For historical OHLCV / MTF market features in this batch, availability is bound
to the close/decision time.

## Batch 16.21d availability

Only the MTF market context is wired from Historical Replay.

The following remain explicit `UNAVAILABLE` placeholders:

- structure;
- derivatives / Rio;
- statistics / Denver;
- portfolio summary;
- market constraints;
- microstructure.

This is intentional. Their parity and historical availability are separate
batches. No value is invented to make the contract look complete.

## Runtime behaviour

A `DecisionContextV1` is frozen only when Scanner emits an opportunity.

The current PAPER pipeline and orchestration still receive the existing
`FeatureSnapshot 1h`. Therefore this batch must not alter Scanner or AI trading
behaviour.

Historical replay points retain the DecisionContext for audit and later wiring.

## Reproducibility

`BacktestConfig.execution_assumptions` additionally binds:

`decision_context_version=decision-context-v1`

The DecisionContext fingerprint binds all current content, provenance,
availability, missing components, MTF feature context and policy versions.

## Validation

```powershell
uv run pytest -q tests/services/decision_context/test_decision_context_models.py
uv run pytest -q tests/backtest/test_replay_runner_mtf.py
uv run pytest -q

uv run python .\scripts\validate_decision_context.py `
  ".\data\historical\binance_spot\backtest_ready\binance_btc_usdc_1m_2025-09-11_2026-09-10.csv"
```
