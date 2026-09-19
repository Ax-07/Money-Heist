# Batch 16.21c — Multi-Timeframe Feature Context

## Objective

Build deterministic per-timeframe `FeatureSnapshot` objects on top of the
16.21b incremental historical MTF cursor.

The Scanner remains strictly `1h`.

The PAPER pipeline / current agents still receive the existing `1h`
`FeatureSnapshot`. This batch only creates and records the richer MTF feature
context at opportunities so the next DecisionContext batch can consume it
without changing trading behaviour.

## Contract

`MultiTimeframeFeatureContext` contains:

- symbol;
- decision timestamp;
- decision timeframe;
- Feature Engine version;
- context contract version;
- source MTF cursor fingerprint;
- requested timeframe set;
- available `FeatureSnapshot` objects;
- explicit missing timeframes;
- explicit warmup-incomplete timeframes;
- deterministic context fingerprint.

Default context version:

`mtf-feature-context-v1`

## Missing and warmup semantics

No value is invented.

If a higher timeframe has no closed candle yet, it is listed in
`missing_timeframes`.

If a timeframe exists but the Feature Engine has insufficient warmup, its
`FeatureSnapshot` is still present with `quality.warmup_complete=False`, and the
timeframe appears in `warmup_incomplete_timeframes`.

With the current Feature Engine configuration the maximum warmup is 35 bars.
Therefore a complete 35-day 1m history is enough for the `1d` FeatureSnapshot
to become fully warmed.

## Runtime placement

The existing `1h` FeatureSnapshot is still computed at every Scanner decision.

The full MTF Feature Context is computed only if the Scanner emits an
opportunity. This avoids recomputing four full feature histories at every hour
while preserving exactly the information later agents need.

The decision `1h` FeatureSnapshot is reused inside the MTF context; it is not
computed twice.

## Reproducibility

MTF replay execution assumptions now additionally bind:

`mtf_feature_context_version=mtf-feature-context-v1`

The context fingerprint binds:

- full FeatureSnapshot payloads;
- missing/warmup state;
- cursor fingerprint;
- feature version;
- context version;
- observed_at;
- decision timeframe.

## Validation

```powershell
uv run pytest -q tests/market/features/test_multitimeframe_context.py
uv run pytest -q tests/backtest/test_replay_runner_mtf.py
uv run pytest -q

uv run python .\scripts\validate_mtf_feature_context.py `
  ".\data\historical\binance_spot\backtest_ready\binance_btc_usdc_1m_2025-09-11_2026-09-10.csv"
```

Scanner parity from Batch 16.21b remains unchanged because Scanner input remains
the same `1h` FeatureSnapshot.
