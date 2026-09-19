# Batch 16.21l — Runtime Historical Rio Activation

## Objective

Activate the historical Kraken derivatives archive in the normal Dashboard and
Ablation runtimes without implicit filesystem discovery.

Rio remains disabled unless the operator explicitly supplies the canonical
archive.

## Dashboard contract

`CampaignRequest` gains optional `derivatives` input:

- `csv_text`;
- `max_age_seconds` (default `7200`).

If absent, behavior is unchanged.

If present, the archive is parsed, validated, symbol-matched to the OHLCV
dataset, fingerprinted into execution assumptions, and the exact validated
object is injected into `HistoricalReplayRunner`.

Only source timeframes capable of the full MTF context are accepted:
`1m`, `5m`, `15m`.

## Runtime contract

`historical-derivatives-runtime-v1` binds:

- context binding version;
- archive version;
- archive fingerprint;
- archive source;
- native instrument;
- max-age seconds.

A missing archive, unbound archive, or fingerprint mismatch fails closed.

## Dashboard UX

The page gains an explicit Rio historical toggle, canonical CSV picker, and
freshness input.

The toggle is OFF by default.

Selecting a file alone does not enable Rio.

## Ablation parity

`PaperAblationRuntimeSettings` may receive the same validated archive object.
Every ablation variant uses the same assumption verification as the baseline.

## Safety invariants

- no automatic local-file discovery;
- no network request during orchestration;
- Scanner stays deterministic 1h;
- native 1h source remains legacy (no fake 15m);
- Risk Engine remains authoritative;
- no funding interpolation;
- liquidation-side fields remain unavailable.

## Validation

```powershell
uv run pytest -q tests/backtest/test_derivatives_runtime_activation.py
uv run pytest -q tests/dashboard/test_mtf_runtime_activation.py
uv run pytest -q tests/dashboard/test_backtest_defaults.py
uv run pytest -q tests/evaluation/test_ablation_campaign_runtime.py
uv run pytest -q

uv run python .\scripts\validate_historical_rio_runtime_activation.py `
  ".\data\historical\kraken_futures\backtest_ready\btc_usdc_pf_xbtusd_1h_2025-09-11_2026-09-11.csv"
```
