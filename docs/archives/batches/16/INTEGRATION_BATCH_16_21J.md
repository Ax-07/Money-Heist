# Batch 16.21j — Historical Derivatives Analytics Archive

## Measured Kraken coverage

A full-period PF_XBTUSD coverage audit was run for:

`2025-09-11T00:00:00Z → 2026-09-11T00:00:00Z`

at 1-hour resolution.

Observed coverage:

- open interest: `8,761 / 8,761` points;
- long/short ratio: `8,761 / 8,761` points;
- funding: `5,052` points;
- first funding point: `2026-02-12T13:00:00Z`;
- funding gap before that point: `3,709` hourly points;
- open-interest gaps: zero;
- long/short-ratio gaps: zero.

## Gap policy

No interpolation, backfill, forward fill beyond freshness policy, or synthetic
derivation from spot OHLCV is permitted.

Before the first real funding point:

- `funding_rate = UNAVAILABLE`;
- `open_interest = AVAILABLE`;
- `open_interest_change_pct = AVAILABLE` when a prior OI sample exists;
- `long_short_ratio = AVAILABLE`.

A Rio projection is therefore `DEGRADED` before funding begins, not unavailable.

After funding begins and while all three core metrics are fresh, Rio may be
`RELIABLE`.

## Liquidations

Kraken's public `liquidation-volume` history is deliberately not mapped to
`long_liquidations_notional` or `short_liquidations_notional`.

The existing Money Heist live adapter already documents that the endpoint is an
aggregate volume series and does not provide a trustworthy directional split.

Both liquidation fields remain explicit missing values.

## Canonical archive

Version:

`historical-derivatives-analytics-v1`

Columns:

```text
symbol
instrument
observed_at
available_at
funding_rate
open_interest
open_interest_change_pct
long_short_ratio
```

The downloader retrieves Kraken public analytics and writes one hourly row for
the complete backtest grid.

## Conservative availability

Default:

`availability_lag_seconds=3600`

An hourly Kraken analytics point timestamped at `T` is therefore usable by
replay only at `T + 1h`.

This avoids treating an hourly bucket as known before it has fully elapsed.

The lag is serialized into every row's `available_at`, so it is auditable and
participates in the archive fingerprint.

## OI change

`open_interest_change_pct` is computed only from the current and immediately
previous real Kraken OI observations:

`(current - previous) / previous * 100`

The downloader fetches one OI point before the requested start boundary so the
first in-period change can be computed without future leakage.

If the previous OI is zero or unavailable, change remains missing.

## Deliberate non-goal

This batch still does not activate Rio inside historical orchestration.

It creates and validates the real historical derivatives dataset first.

The following batch will wire the frozen archive into:

- `DecisionContext.derivatives`;
- Rio specialist context;
- replay execution assumptions;
- agent grounding / provenance.

## Commands

After applying the batch:

```powershell
uv run pytest -q tests/backtest/test_historical_derivatives_analytics.py
uv run pytest -q
```

Download the canonical annual archive:

```powershell
uv run python .\scripts\download_kraken_derivatives_analytics.py `
  ".\data\historical\kraken_futures\backtest_ready\btc_usdc_pf_xbtusd_1h_2025-09-11_2026-09-11.csv"
```

Validate it:

```powershell
uv run python .\scripts\validate_historical_derivatives_analytics.py `
  ".\data\historical\kraken_futures\backtest_ready\btc_usdc_pf_xbtusd_1h_2025-09-11_2026-09-11.csv"
```
