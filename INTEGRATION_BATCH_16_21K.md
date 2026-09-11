# Batch 16.21k — Historical Rio Wiring

## Objective

Wire the real historical Kraken derivatives archive into the historical replay
decision boundary without changing normal Dashboard activation yet.

For an opportunity in MTF replay, one cutoff-safe derivatives snapshot is
selected once and becomes the single source for both:

- `DecisionContext.derivatives`;
- `RioContext` supplied to the Rio specialist.

No network request is performed during orchestration.

## Frozen-snapshot invariant

```text
decision_time
    ↓
HistoricalDerivativesAnalyticsArchive.positioning_snapshot_at(...)
    ↓
ONE frozen DerivativesPositioningSnapshot
    ├── DecisionContext.derivatives
    └── rio_context_from_snapshot(snapshot)
            ↓
       specialist_contexts["rio"]
```

Rio therefore cannot see a derivative value different from the one recorded in
the frozen DecisionContext.

## Availability and lookahead

The archive lookup enforces `available_at <= decision_time` and the runner adds
a freshness limit (`derivatives_max_age`, default 2h).

DecisionContext provenance records real `observed_at`, `available_at`, missing
fields, data quality and archive fingerprint. `DecisionContextV1` rejects any
provenance whose `available_at` is later than decision `as_of`.

## Rio gating

If no fresh usable metric exists, `DecisionContext.derivatives` stays
`UNAVAILABLE` and no Rio specialist context is passed.

If usable:
- pre-funding period: Rio is `DEGRADED`;
- post-funding period: Rio may be `RELIABLE`;
- directional liquidation fields stay unavailable.

The Professor still decides whether Rio is actually selected.

## PAPER relay

`PaperTradingPipeline.run(...)` accepts optional explicit `specialist_contexts`
and forwards them unchanged to orchestration. Risk Engine and broker logic are
untouched.

## Reproducibility

When an archive is injected, replay binds:
- `derivatives_context_binding_version=historical-derivatives-rio-v1`
- archive version
- archive fingerprint
- source
- instrument
- max age seconds

Mismatch fails closed.

## Deliberate non-goal

16.21k does not automatically load the archive from Dashboard or Ablation.
That activation remains a separate batch.

## Validation

```powershell
uv run pytest -q tests/backtest/test_replay_runner_mtf.py
uv run pytest -q tests/paper_pipeline/test_pipeline.py
uv run pytest -q

uv run python .\scripts\validate_historical_rio_wiring.py `
  ".\data\historical\kraken_futures\backtest_ready\btc_usdc_pf_xbtusd_1h_2025-09-11_2026-09-11.csv"
```
