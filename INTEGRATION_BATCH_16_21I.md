# Batch 16.21i — Historical Derivatives Archive Foundation

## Scope

This batch creates the historical data contract required before Rio can be
enabled in historical replay.

It does **not** change agent selection or replay behavior yet.

## Why funding only

Kraken publishes an official downloadable historical funding-rate export for
Derivatives markets since inception.

The project does not currently possess equally validated historical archives
for:

- open interest;
- open-interest change;
- long/short ratio;
- long liquidations;
- short liquidations.

Those fields therefore remain explicitly unavailable.

No metric is reconstructed from spot OHLCV.

## Canonical archive

Version:

`historical-derivatives-funding-v1`

Canonical CSV:

```text
symbol,instrument,observed_at,available_at,funding_rate
BTC/USDC,PF_XBTUSD,...,...,...
```

`observed_at` is the source event timestamp.

`available_at` is the earliest replay timestamp at which the point may be used.

The archive rejects:

- naive timestamps;
- `available_at < observed_at`;
- duplicate observation timestamps;
- mixed symbols/instruments;
- non-finite funding rates;
- non-monotonic availability.

## Anti-lookahead selection

Replay lookup selects by:

`available_at <= decision_time`

not merely by observation timestamp.

A configurable `max_age` then prevents stale funding from being projected into
Rio.

## Rio projection

A funding-only historical point projects to:

- `funding_rate = real archive value`;
- `data_quality = DEGRADED`;
- `is_stale = false` when inside max age;
- open interest = missing;
- long/short ratio = missing;
- liquidations = missing.

This matches the existing Rio contract, where a degraded context with at least
one real metric is usable.

## Kraken raw CSV preparation

The helper:

`scripts/prepare_kraken_funding_archive.py`

normalizes one raw Kraken funding CSV into the canonical archive.

Common timestamp and funding column names are auto-detected. If Kraken's source
header differs, pass:

- `--timestamp-column`;
- `--funding-column`.

The conversion also accepts a non-negative
`--availability-lag-seconds`.

The lag is written into every canonical `available_at`, making the assumption
visible in the data itself rather than hidden in replay code.

## Deliberate non-goals

16.21i does not:

- activate Rio in historical orchestration;
- populate `DecisionContext.derivatives`;
- download external data automatically;
- invent OI, long/short or liquidation history.

Those belong to the next wiring batch after the real archive has been prepared
and validated.

## Validation

```powershell
uv run pytest -q tests/backtest/test_historical_derivatives.py
uv run pytest -q
```

After downloading a real Kraken funding CSV:

```powershell
uv run python .\scripts\prepare_kraken_funding_archive.py `
  ".\path\to\kraken_raw_funding.csv" `
  ".\data\historical\kraken_futures\funding\btc_usd_funding.csv" `
  --symbol "BTC/USDC" `
  --instrument "PF_XBTUSD"
```

Then:

```powershell
uv run python .\scripts\validate_historical_derivatives_archive.py `
  ".\data\historical\kraken_futures\funding\btc_usd_funding.csv"
```
