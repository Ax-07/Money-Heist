# Batch 24A.2 — Rich Indicators & Parity Catalogue

## Status

Implementation overlay prepared against Money Heist `main` / `0c4549663bf43418ff2d337c63343112f314dceb`. No Git push is performed by this batch package.

## Architecture

```text
HistoricalMultiTimeframeCursor / HistoricalMultiTimeframeSlice
                    |
        already-closed canonical candles
                    |
                    v
       app.analytics.indicators
                    |
          typed IndicatorValue[]
                    |
      AnalyticsIndicatorSnapshot
                    |
      AnalyticsSnapshot.components
             ["indicators"]
```

The engine never downloads data, fills gaps, resamples timeframes, reads forward outcomes, imports trading authority, or modifies production features. The caller supplies the exact candle series already made visible by Money Heist at `as_of`.

## Registry identity

The registry exposes both:

- `ANALYTICS_INDICATOR_REGISTRY_VERSION`
- `ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT`
- `ANALYTICS_INDICATOR_REGISTRY_IDENTITY = version@sha256:<fingerprint>`

`indicator_component_versions()` installs the composite identity into the 24A.1 `AnalyticsComponentVersions.indicator_registry_version`. This means a material definition/parameter change changes the registry fingerprint and therefore the Analytics run identity, while the source `BacktestRun.run_id` and business fingerprint stay outside the Analytics identity path.

## Typed contracts

`IndicatorValue` records:

- `indicator_id`
- `value`
- `available`
- `warmup_complete`
- `definition_version`

`AnalyticsIndicatorSnapshot` records:

- `symbol`
- `timeframe`
- `as_of`
- `source_cursor_fingerprint`
- registry version/fingerprint
- visible candle count
- canonical ordered indicator values
- `snapshot_fingerprint`

The typed indicator snapshot is embedded as `AnalyticsSnapshot.components["indicators"]`. The 24A.1 snapshot schema itself is not changed, preserving existing 24A.1 artifacts and empty-component fingerprints.

## Causality

Before parsing OHLCV, the engine checks each candle's `close_time`. OHLCV on candles later than `as_of` is not parsed. Thus future values cannot alter the state at T, including through malformed future-value exception side channels.

Only closed visible candles are used:

```text
candle.is_closed == true
and
candle.close_time <= as_of
```

The engine contains no timeframe resampler. MTF construction remains owned by Money Heist.

## Warmup rules

Warmup is explicit per registry definition. Examples:

- SMA/EMA N: N bars
- EMA slope N: N+1 bars
- RSI14: 15 bars
- RSI delta: 16 bars
- ROC12: 13 bars
- MACD line: 26 bars
- MACD signal/histogram: 34 bars
- ATR14: 14 bars
- Bollinger20: 20 bars
- +DI/-DI14: 15 bars
- ADX14: 28 bars
- Stoch RSI K: 30 bars
- Stoch RSI D: 32 bars
- MFI14: 15 bars
- CMF/VWAP/Volume SMA20: 20 bars
- previous range/Donchian20: 21 bars

A completed warmup does not guarantee availability when the formula has an undefined denominator. Undefined values remain `None`; they are never replaced with zero.

## Indicator families

The registry includes:

- Trend: SMA 20/50/100/200, EMA 9/20/50/100/200, EMA distance/slope.
- Momentum: RSI/delta, Stochastic RSI K/D, ROC12, MACD line/signal/histogram.
- Volatility/strength: ATR/ATR%, Bollinger, ADX/+DI/-DI.
- Volume: Volume SMA/Ratio, OBV, MFI14, CMF20, rolling VWAP20.
- Light structure: previous rolling high/low 20/50/100, Donchian20 and position, distance to previous high/low20.

Technical Events, ZigZag, pattern lifecycle, pattern detection and forward outcomes remain out of scope.

## Validation

After applying the overlay from repository root:

```powershell
uv sync
uv run pytest tests/analytics/indicators -q
uv run pytest tests/analytics -q
uv run pytest -q
```

Then run the repository's configured lint/type-check commands (for example those already used by the project CI / `pyproject.toml`). Finally inspect:

```powershell
git status --short
git diff --stat
git diff
```

Suggested commit after human validation:

```text
feat(analytics): add rich indicator engine and parity catalogue
```
