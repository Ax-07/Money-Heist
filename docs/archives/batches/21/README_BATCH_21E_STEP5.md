# Batch 21e — Step 5 — Historical Master PAPER Execution / Single-Capital Accounting

Baseline: `647486a` — Step 4 Historical Reservation & Arbitration Bridge plus synchronized agent docs.

## Goal

Execute only historical proposals already admitted by the existing Master Portfolio chain while using
one physical PAPER account and one physical Master capital truth.

The Step 5 path is:

`CANDLE_CLOSE -> Step 3 local Risk evidence -> Step 4 reservation + Master arbitration ->
Master ADMIT -> Step 5 Master PAPER entry`.

A local Risk authorization alone is not executable. A Step 4 reservation alone is not executable.
Only an exact Step 4 `ADMIT` outcome whose reservation is still `COMMITTED` may reach PAPER.

## One physical Master account

`MasterHistoricalPaperRuntime` owns exactly one existing `PaperBroker` configured with:

- `system_id = master_portfolio_id`;
- `initial_balance = plan.master_initial_capital`;
- the exact maker fee, taker fee and market slippage from the replay plan;
- deterministic replay IDs and the exact historical barrier clock.

Source `BacktestRun.config.initial_balance` values are never read as execution balances and are never
summed. They remain source-branch provenance only.

The broker order therefore belongs to the Master account. The originating crew remains preserved in
`MasterHistoricalPaperExecutionAttempt.source_system_id` and never becomes a second cash account.

## Exact historical execution boundary

Step 5 consumes the exact raw candle for the Step 3/4 decision barrier. It reuses
`canonical_candle_rows()` and requires its canonical fingerprint to equal the Step 2 timeline candle
fingerprint. Execution uses the exact `CANDLE_CLOSE` mark and exact CLOSE timestamp.

The supplied proposal evidence must match the set of Master-admitted candidates exactly and preserve
all Step 3 proposal fingerprints and provenance. Missing, extra, duplicated or altered proposal
evidence fails before any order is submitted.

Execution order is the existing Batch 21d arbitration outcome order. Step 5 adds no ranking rule.

## Risk quantity is immutable

The PAPER order quantity is exactly `MasterRiskGateCandidate.local_approved_quantity`, which is the
quantity already authorized by the deterministic local Risk Engine and preserved by the veto-only
Master Risk Gate.

Step 5 cannot resize, increase, reinterpret or re-authorize that quantity.

## Physical cash preflight

The existing `PaperBroker` uses spot-style cash accounting for BUY orders. Before a historical LONG
entry, Step 5 computes the exact expected cash debit from:

- the exact CLOSE mark;
- replay-plan market slippage;
- replay-plan taker fee;
- the exact Risk-authorized quantity.

If the physical Master cash balance is insufficient, the order is not sent to the broker. The
candidate's already-`COMMITTED` reservation is released at the exact barrier timestamp with a
deterministic release reference.

This is a post-admission execution veto caused by physical accounting, not a Risk override. It can
only prevent execution; it cannot loosen Risk or create additional buying power. Successful entries
keep their reservation `COMMITTED` unchanged.

Unexpected broker failures after the deterministic preflight are fail-hard. Step 5 does not invent a
transaction rollback model that the existing broker does not provide.

## Signed PAPER semantics

The Master runtime reuses the existing `PaperBroker` signed-position model and enables its existing
short support. LONG and SHORT source crews therefore execute against one physical account and may
net at broker position level. Source-crew attribution remains in the immutable Step 5 execution
evidence.

This does not create per-crew broker cash or per-crew equity.

## Master account snapshots

`MasterHistoricalPaperAccountSnapshot` seals, from the single Master broker:

- initial balance;
- cash balance;
- equity;
- UTC day-start equity;
- equity peak;
- daily PnL;
- realized and unrealized PnL;
- fees paid;
- gross exposure;
- open-position count.

It can project its capital fields to the existing `MasterCapitalSnapshot` through
`to_master_capital_snapshot()`. No branch equity participates in that projection.

## Idempotency

An exact replay of the same Step 4 result, exact candle and exact admitted proposal evidence on the
same runtime returns the already sealed result and creates no duplicate PAPER order or fill.

A conflicting replay or a ledger that diverged from the previously sealed final ledger fails closed.

## Explicit Step 5 limitation

Step 5 executes and accounts for **entries only**.

It deliberately does not reuse `HistoricalPositionLifecycle` because that component is single-system,
requires its broker `system_id` to equal the source system and stores protections by symbol. Reusing
it for several crews trading the same Master symbol would collapse distinct crew protections.

Therefore Step 5 does not yet implement:

- multi-crew stop/target lifecycle;
- per-crew virtual lots inside the net physical Master position;
- release of committed reservation exposure when a historical position exits;
- multi-barrier exposure reconciliation driven from those virtual lots.

Those belong to a later Step 6. Until that layer exists, Step 5 is the safe entry-execution and
single-capital accounting foundation, not the complete end-to-end Master backtest lifecycle.

## Authority invariants

Step 5:

- executes PAPER only;
- has no LIVE path;
- has no Risk authority;
- has no Master admission authority;
- has no registry authority;
- never sums branch equities;
- never creates a branch broker;
- never infers additional capital or leverage;
- never auto-promotes or mutates agent configuration.

`paper_broker_authority = True` means only that this bounded Step 5 execution service is the component
allowed to submit already-admitted PAPER orders to its one Master `PaperBroker`. It grants no LIVE or
Risk authority.

## Contracts

Step 5 adds:

- `MasterHistoricalPaperRuntimeIdentity`;
- `MasterHistoricalPaperProposalEvidence`;
- `MasterHistoricalPaperAccountSnapshot`;
- `MasterHistoricalPaperAttemptStatus`;
- `MasterHistoricalPaperReasonCode`;
- `MasterHistoricalPaperExecutionAttempt`;
- `MasterHistoricalPaperExecutionStatus`;
- `MasterHistoricalPaperExecutionResult`;
- `MasterHistoricalPaperRuntime`;
- `build_master_historical_paper_runtime()`;
- `execute_master_historical_paper_admissions()`.

Persisted contracts use deterministic SHA-256 fingerprints.

## Validation in generation harness

- `tests/portfolio/test_master_historical_replay_paper_execution.py`: 38 passed;
- all reconstructed `tests/portfolio`: 477 passed;
- Python 3.13 compilation: passed;
- Python source/test line length <= 100: passed.

Ruff is not installed in the generation harness. Run Ruff and the complete repository suite in the
real checkout before commit.
