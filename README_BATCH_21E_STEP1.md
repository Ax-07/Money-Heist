# Batch 21e — Step 1 — Master Historical Replay Contracts

Baseline: `d9499ce` — Concurrent Arbitration Audit & Closure.

## Goal

Define the immutable input plan for a future coordinated Master Portfolio historical replay without
replacing the existing single-system `HistoricalReplayRunner` or
`BacktestPortfolioStateProvider`.

This step does not replay candles, evaluate Risk, reserve capacity, arbitrate candidates, mutate a
broker, submit orders, or provide LIVE authority.

## Reuse of the existing replay stack

The existing historical runner remains the chronological single-system replay primitive. Existing
`BacktestRun` objects are consumed structurally through their already-canonical dataset/config
payloads; no second BacktestRun model or parallel replay engine is introduced.

The V1 Master plan coordinates those source runs above the existing stack.

## Single Master capital truth

`MasterHistoricalReplayPlan.master_initial_capital` is an explicit, operator-supplied amount and is
the only physical capital truth of the future Master replay.

Every source `BacktestRun.config.initial_balance` is retained only as historical branch provenance in
`MasterHistoricalReplayCrewRef.source_branch_initial_balance`.

The contracts explicitly expose:

- `single_master_capital = True`;
- `sums_branch_equities = False`;
- `branch_initial_balance_is_master_capital = False`;
- each crew ref has `branch_equity_summable = False` and `branch_capital_authority = False`.

No SHADOW/backtest branch equity is added to Master capital and no branch balance becomes an
allocation automatically.

## Coordinated V1 timeline

V1 deliberately supports one exact shared historical dataset and one exact shared replay period.
Every crew source run must use the same canonical `DatasetRef` and period bounds.

This avoids inventing cross-market clock alignment rules before the project has a dedicated
multi-dataset synchronization contract.

## Shared execution environment

All source runs must also agree on execution assumptions that would belong to one future shared
physical execution environment:

- execution model version;
- maker fee;
- taker fee;
- market slippage;
- intrabar policy.

Crew-specific Risk, feature, prompt, model, or other strategy configuration may differ. Each complete
source `BacktestConfig` canonical payload receives its own immutable fingerprint.

## Policy provenance

A READY plan requires already-configured Batch 21 policies:

- `MasterAllocationPolicy`;
- `MasterRiskGatePolicy`;
- `MasterArbitrationPolicy`.

All three must belong to the same Master Portfolio, and the gate/arbitration policies must bind to
exactly the supplied allocation-policy fingerprint.

The set of source-run `system_id` values must match the allocation-policy membership exactly: one
source run per crew, no missing crew, no duplicate crew, no extra crew.

## Contracts

Step 1 adds:

- `BacktestRunLike` structural protocol;
- `MasterHistoricalReplayPlanStatus`;
- `MasterHistoricalReplayMode`;
- `MasterHistoricalReplayCrewRef`;
- `MasterHistoricalReplayPlan`;
- `build_master_historical_replay_plan()`.

The plan and every crew reference have deterministic SHA-256 fingerprints. Input source-run order is
canonicalized by `system_id`, so caller ordering does not change the plan identity.

## Authority invariants

The plan is immutable configuration/provenance only:

- `mutation_applied = False`;
- `risk_authority = False`;
- `admission_authority = False`;
- `reservation_mutation = False`;
- `broker_authority = False`;
- `registry_mutation = False`;
- `live_authority = False`;
- `auto_execute = False`.

## Next step

Step 2 should add a deterministic Master replay timeline/coordinator that consumes this plan while
continuing to reuse the existing historical replay primitives. It must not sum branch equities or
silently share one existing single-system `PaperBroker` across crews.

## Validation in generation harness

- `tests/portfolio/test_master_historical_replay_contracts.py`: 32 passed;
- all `tests/portfolio`: 331 passed;
- Python compilation: passed;
- Python source line length <= 100: passed.

Ruff and the complete repository suite must still be run in the real checkout before commit.
