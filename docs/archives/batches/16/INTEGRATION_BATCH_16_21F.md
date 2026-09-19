# Batch 16.21f — Historical Market Structure / Nairobi Context

## Objective

Replace the `DecisionContext.structure = UNAVAILABLE` placeholder with a
deterministic structure context derived only from already-closed OHLCV candles.

This batch does **not** claim access to order-book depth, liquidation feeds or
true liquidity data. `DecisionContext.microstructure` remains `UNAVAILABLE`.

## Structure V1

For each configured MTF timeframe (`15m`, `1h`, `4h`, `1d`), V1 exposes:

- current close;
- prior 20-candle high / low;
- range location;
- breakout state;
- retest / false-break proxy;
- strict confirmed pivot highs and lows;
- HH/HL, LH/LL, MIXED or UNKNOWN swing structure;
- explicit missing fields;
- explicit `orderbook_available=false`;
- explicit `liquidation_data_available=false`.

Default version:

`market-structure-v1`

## Anti-lookahead

Only candles already present in `HistoricalMultiTimeframeCursor` are accepted.

Every candle used by the structure engine must satisfy:

`candle.close_time <= structure.observed_at`

and the cursor `as_of` must exactly equal the structure `observed_at`.

Local pivots require candles on both sides of the pivot. This does not create
lookahead at the decision boundary because a pivot is emitted only after those
right-hand candles have themselves closed and are already visible.

## DecisionContext wiring

At an opportunity:

1. build MTF Feature Context;
2. build Market Structure Context from the same frozen MTF cursor;
3. mark `DecisionContext.structure = AVAILABLE`;
4. attach structure provenance with `available_at = as_of`;
5. build the frozen DecisionContext;
6. propagate it through the already-validated Batch 16.21e agent path.

The DecisionContext now also rejects any optional section marked `AVAILABLE`
unless that section has provenance.

## Nairobi semantics

Nairobi may ground evidence at paths such as:

`market_context.decision_context.structure.payload.timeframes.1h.swing_structure`

or:

`market_context.decision_context.structure.payload.timeframes.4h.breakout_state`

Order-book, liquidation and other microstructure evidence remains unavailable
and must not be inferred.

## Reproducibility

MTF replay execution assumptions additionally bind:

`market_structure_version=market-structure-v1`

## Validation

```powershell
uv run pytest -q tests/market/test_market_structure_context.py
uv run pytest -q tests/services/decision_context/test_decision_context_models.py
uv run pytest -q tests/backtest/test_replay_runner_mtf.py
uv run pytest -q

uv run python .\scripts\validate_market_structure_context.py `
  ".\data\historical\binance_spot\backtest_ready\binance_btc_usdc_1m_2025-09-11_2026-09-10.csv"
```
