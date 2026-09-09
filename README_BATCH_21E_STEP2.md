# Batch 21e — Step 2 — Master Historical Replay Coordinator

Baseline: `0c7bf96` — Master Historical Replay Contracts.

## Goal

Add the deterministic shared historical clock used by the future Master Portfolio replay without
running any crew trading pipeline, mutating reservations, evaluating Risk, touching a broker, or
providing LIVE authority.

The coordinator consumes the Step 1 `MasterHistoricalReplayPlan`, the exact bound historical
dataset, and its candle rows. It produces one immutable `MasterHistoricalReplayTimeline` shared by
all crews.

## Why Step 2 stops before branch execution

The existing `HistoricalReplayRunner` is intentionally single-system and currently calls the full
`PaperTradingPipeline` for each opportunity. That PAPER pipeline continues through local Risk and
broker execution in one call.

Running complete crew replays independently and arbitrating their trades afterward would therefore
be incorrect: execution would already have happened inside isolated crew brokers before Master
capital reservation and arbitration.

Step 2 avoids that architectural error. It establishes the exact shared timeline first. A later
step can attach a pre-execution crew adapter to the CLOSE barrier, collect locally Risk-authorized
candidates from every crew, then use the existing Batch 21b/21c/21d reservation and arbitration
chain before any admitted PAPER execution.

## Reuse of historical dataset semantics

The coordinator reuses the existing backtest dataset primitives:

- `canonical_candle_rows()` for canonical ordering and OHLC validation;
- `DatasetRef.from_candles()` for content-address verification.

It does not introduce a second candle canonicalizer or another historical data identity model.

The supplied dataset must match the Step 1 plan exactly by:

- canonical `DatasetRef` fingerprint;
- content SHA-256;
- symbol;
- timeframe.

The supplied candle rows are re-hashed and must reproduce the same dataset content, candle count,
start time, and end time.

Only closed candles are accepted.

## Shared OPEN/CLOSE barriers

Every replayed candle creates exactly two barriers for every crew:

1. `CANDLE_OPEN` at the candle open time;
2. `CANDLE_CLOSE` at the candle close time.

The crew list is canonical and identical on every barrier.

OPEN barriers are never trade-decision eligible. A CLOSE barrier is decision eligible only when its
close time is within the configured replay period.

Candles before `period_start` remain in the timeline as historical warmup/lifecycle context, matching
the existing runner's chronological behavior. Candles whose close is after `period_end` are not
replayed.

A replay period with no completed candle is valid and produces an empty barrier sequence instead of
inventing a minimum history requirement.

## Chronology

For the portion actually replayed, candles must not overlap:

`next.open_at >= previous.close_at`

This matches the dynamic historical replay constraint needed by position lifecycle processing and
prevents different crews from observing contradictory OPEN/CLOSE clock states.

The coordinator does not invent a concurrency time window. Concurrency in future Master arbitration
will come from candidates produced at the same explicit CLOSE barrier.

## Deterministic contracts

Step 2 adds:

- `HistoricalReplayDatasetLike`;
- `MasterHistoricalReplayBarrierPhase`;
- `MasterHistoricalReplayTimelineStatus`;
- `MasterHistoricalReplayBarrier`;
- `MasterHistoricalReplayTimeline`;
- `MasterHistoricalReplayCoordinator`;
- `build_master_historical_replay_timeline()`.

Every candle row, barrier, and complete timeline is deterministically fingerprinted. Reordering the
caller-supplied candle sequence does not change the result because the existing dataset
canonicalization defines source order.

The timeline identity also binds the complete Step 1 plan fingerprint, so changing Master capital,
crew membership, policy provenance, or any other material plan input changes the timeline identity.

## Capital boundary

The coordinator never reads or sums branch broker equities.

The Step 1 plan remains the sole source of Master capital truth:

`MasterHistoricalReplayPlan.master_initial_capital`

The timeline only binds to that plan by ID and fingerprint. It exposes:

- `single_master_capital = True`;
- `sums_branch_equities = False`.

No source `BacktestRun.config.initial_balance` becomes cash, allocation, or executable buying power.

## Authority invariants

The coordinator and timeline are scheduling/provenance only:

- `executes_branch_pipeline = False`;
- `mutation_applied = False`;
- `risk_authority = False`;
- `admission_authority = False`;
- `reservation_mutation = False`;
- `broker_authority = False`;
- `registry_mutation = False`;
- `live_authority = False`;
- `auto_execute = False`.

No Master Risk Gate decision, reservation transition, broker submission, or LIVE path is introduced
by Step 2.

## Next step

Step 3 should add the pre-execution historical crew bridge used at CLOSE barriers. It must collect
crew-local outcomes up through the existing deterministic local Risk boundary while preventing the
crew PAPER broker from executing before Master reservation/arbitration. Locally rejected trades must
remain terminal, and locally authorized candidates must still pass the existing Master reservation,
Risk Gate, and arbitration chain before any PAPER execution.

## Validation in generation harness

- `tests/portfolio/test_master_historical_replay_coordinator.py`: 33 passed;
- all `tests/portfolio`: 364 passed;
- Python 3.13 compilation: passed;
- Python source line length <= 100: passed.

Ruff is not installed in the generation harness. Run Ruff and the complete repository suite in the
real checkout before commit.
