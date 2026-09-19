# Batch 16.21b — Historical Replay Multi-Timeframe Wiring

## Objective

Wire the Batch 16.21a deterministic MTF foundation into Historical Replay
without changing the strategy decision timeframe.

Candidate policy for this batch:

- canonical historical source: `1m`;
- lifecycle / intrabar replay: `1m`;
- Scanner decision timeframe: `1h`;
- MTF availability: `15m / 1h / 4h / 1d`;
- MTF policy: `mtf-utc-closed-v1`.

The Scanner still receives one `1h` FeatureSnapshot. Agents still receive the
same single-timeframe market context as before. Multi-timeframe agent features
belong to Batch 16.21c+.

## Reproducibility contract

MTF mode is opt-in on `HistoricalReplayRunner`.

The `BacktestConfig.execution_assumptions` must bind:

```text
historical_source_timeframe=1m
decision_timeframe=1h
mtf_timeframes=15m,1h,4h,1d
mtf_policy_version=mtf-utc-closed-v1
lifecycle_timeframe=1m
```

`execution_assumptions` already participates in
`BacktestConfig.canonical_payload`, therefore these values participate in
`BacktestRun.run_id`.

## Runtime rules

For every source `1m` candle:

1. historical position lifecycle is processed on the source candle;
2. the ReplayClock advances normally;
3. the incremental MTF cursor consumes the closed source candle once;
4. no market decision occurs unless a complete `1h` candle closed exactly at
   that ReplayClock;
5. Feature Engine and Scanner receive only cumulative closed `1h` candles;
6. the replay point records MTF counts and the compact cursor fingerprint.

This keeps opportunity generation directly comparable with a native `1h`
replay while allowing later batches to consume the MTF state.

## Validation

```powershell
uv run pytest -q tests/market/test_multitimeframe_cursor.py
uv run pytest -q tests/backtest/test_replay_runner_mtf.py
uv run pytest -q
```

Expected invariant: a deterministic `1m -> 1h` MTF replay produces exactly the
same Feature Engine call sequence and Scanner call sequence as replaying the
equivalent native `1h` series when execution/portfolio side effects are not
part of that comparison.
