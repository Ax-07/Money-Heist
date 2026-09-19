# Batch 16.21a — Historical Multi-Timeframe Dataset Foundation

## Scope

This batch adds deterministic historical multi-timeframe construction only.

It does **not** change:

- Scanner cadence or thresholds;
- Feature Engine behaviour;
- agent prompts or orchestration;
- Risk Engine;
- PAPER/LIVE execution.

## Contract

A contiguous closed source candle series (currently intended to be `1m`) can be
resampled into fixed UTC-aligned higher timeframes.

Rules:

1. source candles must be closed, chronological, same symbol/timeframe and
   exactly contiguous;
2. target timeframe must be an exact multiple of the source timeframe;
3. only source candles with `close_time <= as_of` are visible **and validated**;
4. incomplete edge buckets are dropped;
5. internal gaps are rejected;
6. OHLCV aggregation is deterministic;
7. the resulting historical MTF slice is immutable and fingerprinted;
8. source and MTF fingerprints bind the exact visible source content,
   policy version, `as_of`, timeframe set and derived candle content;
9. future candles cannot influence an earlier result, including through
   validation failures.

Default candidate context set remains `15m / 1h / 4h / 1d`, without making it
the final strategy decision for OPEN-006.

## Reference local dataset

Expected validation dataset:

`data/historical/binance_spot/backtest_ready/binance_btc_usdc_1m_2025-09-11_2026-09-10.csv`

Expected complete-year counts when aligned on UTC boundaries:

- 15m: 35,040
- 1h: 8,760
- 4h: 2,190
- 1d: 365

These counts are a local integration check, not embedded in unit tests.

## Validation

```powershell
uv run pytest -q tests/market/test_multitimeframe.py tests/market/test_historical.py
uv run pytest -q

uv run python .\scripts\validate_mtf_dataset.py `
  ".\data\historical\binance_spot\backtest_ready\binance_btc_usdc_1m_2025-09-11_2026-09-10.csv"
```

The historical replay runner is intentionally not wired to this builder yet.
That wiring belongs to the following parity batch after this foundation is
validated.
