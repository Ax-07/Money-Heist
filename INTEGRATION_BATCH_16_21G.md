# Batch 16.21g — Runtime MTF Activation

## Why this batch exists

Batches 16.21a–f implemented and validated the MTF stack, but the production
Dashboard and Ablation runtime constructors still instantiated
`HistoricalReplayRunner` without `decision_timeframe`.

That meant the MTF path existed and passed dedicated tests but was not yet
activated by ordinary campaign execution.

## Activation policy

Full MTF runtime targets:

`15m,1h,4h,1d`

Primary decision cadence:

`1h`

The full runtime is enabled only when the historical source can deterministically
produce every target timeframe:

- `1m` → enabled;
- `5m` → enabled;
- `15m` → enabled;
- `30m` → legacy;
- `1h` → legacy;
- `4h` → legacy;
- `1d` → legacy.

A native `1h` source can never be used to fabricate `15m`.

## Versioned runtime contract

Enabled runs bind:

- `mtf_runtime_version=historical-mtf-runtime-v1`;
- `historical_source_timeframe=<source>`;
- `decision_timeframe=1h`;
- `mtf_timeframes=15m,1h,4h,1d`;
- `mtf_policy_version=mtf-utc-closed-v1`;
- `mtf_feature_context_version=mtf-feature-context-v1`;
- `decision_context_version=decision-context-v1`;
- `agent_context_binding_version=decision-context-agent-binding-v1`;
- `market_structure_version=market-structure-v1`;
- `lifecycle_timeframe=<source>`.

## Dashboard

Compatible datasets record the MTF assumptions in `BacktestConfig` and ordinary
campaign execution reconstructs the MTF runner mode from that contract.

A native 1h dataset remains on the previous single-timeframe path.

## Ablation

Ablation variants preserve the source run's execution assumptions. The ablation
runtime now reconstructs its runner mode from those same assumptions, preventing
baseline and agent-removal variants from silently using a different timeframe
contract.

## Test compatibility

Dashboard UX/control tests use short synthetic campaigns whose purpose is to
exercise progress and agent-trace rendering, not MTF warmup semantics. Their
fixtures therefore use native `1h` legacy replay with enough bars to exercise
the agents.

Dedicated Batch 16.21g tests separately prove that `1m` activates the full MTF
runtime and that native `1h` does not fabricate `15m`.

## Validation

```powershell
uv run pytest -q tests/backtest/test_mtf_runtime_activation.py
uv run pytest -q tests/dashboard/test_mtf_runtime_activation.py
uv run pytest -q

uv run python .\scripts\validate_mtf_runtime_activation.py `
  ".\data\historical\binance_spot\backtest_ready\binance_btc_usdc_1m_2025-09-11_2026-09-10.csv"
```
