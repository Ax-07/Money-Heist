# Batch 21e — Step 7 — Coordinated Multi-Barrier Replay & Master Evaluation

Baseline: `f60532d` — Step 6 Historical Multi-Crew Lifecycle & Virtual Lots.

## Goal

Assemble the Batch 21e primitives into one deterministic chronological Master historical replay
while
preserving one physical PAPER account, one Master capital truth and per-crew virtual attribution.

The Step 7 loop is:

`OPEN lifecycle -> CLOSE lifecycle -> current Master snapshot -> historical crew input -> Step 3
local
Risk evidence -> Step 4 reservation + Master arbitration -> Step 5 PAPER entry -> Step 6 virtual-lot
registration -> next barrier`.

The loop never creates one broker or one equity balance per crew.

## Exact chronology

Every timeline barrier is processed in order, including warm-up candles. The runner delegates all
existing stop/target behavior to Step 6 before evaluating a new CLOSE decision.

For a decision-eligible `CANDLE_CLOSE`, the ordering is therefore strictly:

1. process exits already open before this candle;
2. mark the one Master PAPER account to the exact close;
3. build the current virtual-lot Master Portfolio snapshot;
4. obtain caller-supplied historical crew evidence bound to that exact snapshot;
5. build the Step 3 decision barrier;
6. reserve explicit capital requirements and run the existing Step 4 Master arbitration;
7. execute only Step 4 `ADMIT` outcomes through Step 5;
8. register only executed Step 5 entries as Step 6 virtual lots;
9. seal the post-entry portfolio and equity point.

An exit occurring on a CLOSE therefore frees its reservation before new reservations at that same
CLOSE. A position opened at that CLOSE remains protected from retrospective use of the candle's
already-known high/low by the Step 6 entry-candle rule.

## Historical input port

`MasterHistoricalBarrierInputSource` is an asynchronous port. It is called only for
decision-eligible
CLOSE barriers and receives the exact current `MasterPortfolioSnapshot`.

It returns a fingerprinted `MasterHistoricalBarrierInput` containing:

- one `HistoricalCrewPreExecutionEvidence` per configured crew;
- the exact current portfolio snapshot fingerprint;
- explicit `MasterHistoricalCapitalRequirement` objects;
- an auditable source reference.

Step 7 does not call an AI provider directly. A future adapter may satisfy this port from MOCK,
CACHED
or existing AI-Gateway-backed orchestration, but provider access remains outside the Master runner.

The input port does not grant Risk, admission, broker or LIVE authority.

## Current portfolio binding

Every input frame must bind the exact portfolio snapshot passed to the input source. A stale or
substituted snapshot fingerprint fails closed before reservation or PAPER execution.

This makes the chronological dependency explicit:

`previous fills/exits -> current Master state -> next crew evidence`.

Step 7 cannot prove how an external implementation internally computed its evidence, but it seals
the
exact state that was supplied to that implementation and requires its returned frame to bind that
state.

## Explicit capital requirements

Step 7 preserves the Step 4 rule that capital requirements are explicit operator-owned inputs.

It does not infer capital from:

- approved notional;
- branch initial balance;
- local Risk amount;
- current Master cash;
- leverage assumptions.

The requirement set must exactly match the candidate seeds produced by Step 3. Missing or extra
requirements fail through the existing Step 4 validation.

## One physical Master account

The runner builds exactly one existing `MasterHistoricalPaperRuntime` and one existing
`MasterHistoricalVirtualLotBook`.

Source `BacktestRun.config.initial_balance` values remain provenance only and are never summed.

The Master initial capital is exactly `plan.master_initial_capital` and the final Master account net
PnL is exactly:

`final Master PAPER equity - Master initial capital`.

## Reservation and exposure reconciliation

The current Master snapshot comes from Step 6 virtual lots rather than the broker's net physical
position.

Therefore opposing crew lots remain visible in gross exposure even if the physical PAPER position
nets to zero.

If marked virtual gross exposure rises above the amount represented by committed reservations, the
existing Master Risk Gate reconciliation becomes `INCONSISTENT`. New candidates are then rejected
fail-closed through the existing Step 21c evaluator. Step 7 does not enlarge reservations or invent
new capacity.

At replay completion:

- every open virtual lot must have exactly one `COMMITTED` reservation;
- every `COMMITTED` reservation must belong to an open virtual lot;
- no reservation may remain merely `RESERVED`.

## Decision-cycle audit chain

Every decision-eligible CLOSE produces one `MasterHistoricalDecisionCycle` binding:

- the exact historical barrier input;
- the pre-admission Master Portfolio snapshot;
- the Step 3 decision barrier;
- the Step 4 reservation/arbitration result;
- the Step 5 PAPER execution result;
- the Step 6 virtual-lot registration result;
- the post-entry Master Portfolio snapshot.

The cycle is fingerprinted from the fingerprints of those existing boundaries rather than replacing
them with a parallel execution engine.

## Equity curve and drawdown

Step 7 records one `MasterHistoricalEquityPoint` after every replay barrier from the one physical
Master PAPER account.

For maximum drawdown, Step 7 reuses the existing evaluation layer's public `EquityPoint`, `Metric`
and `calculate_trading_metrics()` contracts. It does not create a second drawdown convention.

The resulting evaluation exposes:

- final Master equity;
- Master account net PnL;
- return percentage;
- maximum drawdown absolute and percentage;
- fees paid;
- final open risk;
- final virtual gross exposure.

## Virtual-lot trade evaluation

The existing generic evaluation trade reconstruction cannot safely reconstruct per-crew trades from
the Master broker fills because those fills represent one physically netted account.

Step 7 therefore uses Step 6 virtual lots as the authoritative attribution source for:

- closed/open lot counts;
- winning, losing and breakeven lots;
- closed-lot realized net PnL;
- win rate;
- profit factor;
- expectancy;
- per-crew entry/closed/open counts;
- per-crew realized net PnL;
- per-crew final open risk and gross exposure.

Metric availability semantics reuse the existing `Metric` contract. With no closed virtual lots,
win rate, profit factor and expectancy are explicitly `UNAVAILABLE` rather than fabricated as zero.

## Accounting closure invariants

`MasterHistoricalEvaluation` rejects incomplete accounting. In particular:

`local authorized = NOT_RESERVED + MASTER_REJECT + MASTER_ADMIT`

and:

`MASTER_ADMIT = PAPER_EXECUTED + CASH_BLOCKED`.

It also requires:

`PAPER entries = closed virtual lots + open virtual lots`.

Per-crew lot counts, realized PnL, open risk and gross exposure must sum back to the Master
virtual-lot
figures.

## AI economics boundary

Step 7 does not invent AI costs from orchestration evidence.

`ai_cost_eur` is explicitly `UNAVAILABLE` with reason
`AI_USAGE_NOT_SUPPLIED_BY_STEP7_INPUT_PORT`, and `economic_net` remains unavailable until exact AI
usage/cost evidence is supplied through an appropriate existing evaluation adapter or a later
integration step.

Trading evaluation is therefore available without pretending that AI economics have been measured.

## Determinism and fail-closed behavior

The runner validates before execution that:

- allocation, Master Risk Gate and arbitration policies still match the sealed plan;
- timeline membership matches allocation membership;
- every supplied raw candle reproduces the exact timeline candle fingerprint;
- barriers are consumed through the existing Step 6 contiguous lifecycle;
- historical input frames bind the exact current portfolio snapshot;
- Step 3/4/5/6 provenance fingerprints remain connected;
- final committed reservations exactly match open virtual lots.

Fresh reruns with the same plan, timeline, candles and deterministic input source produce the same
result fingerprint.

## Authority invariants

Step 7:

- does not override local deterministic Risk;
- does not resize a Risk-authorized quantity;
- does not create a new Master admission rule;
- uses the existing veto-only Master Risk Gate;
- does not create a broker per crew;
- does not sum branch equities;
- does not mutate AgentRegistry;
- does not promote agents;
- has no LIVE path;
- cannot arm LIVE;
- cannot create a first real order.

PAPER broker calls occur only inside the already-bounded Step 5 entry and Step 6 exit services.

## Contracts

Step 7 adds:

- `MasterHistoricalBarrierInputSource`;
- `MasterHistoricalBarrierInput`;
- `MasterHistoricalDecisionCycle`;
- `MasterHistoricalEquityPoint`;
- `MasterHistoricalCrewEvaluation`;
- `MasterHistoricalEvaluation`;
- `MasterHistoricalCoordinatedReplayStatus`;
- `MasterHistoricalCoordinatedReplayResult`;
- `build_master_historical_barrier_input()`;
- `run_master_historical_coordinated_replay()`.

Persisted Step 7 records use deterministic SHA-256 fingerprints.

## Validation in generation harness

- `tests/portfolio/test_master_historical_replay_master_runner.py`: 28 passed;
- all reconstructed `tests/portfolio`: 536 passed;
- Python compilation: passed;
- Python source/test line length <= 100: passed.

The reconstruction harness contains a minimal evaluation compatibility stub only for running the
Portfolio test slice. The real checkout contains the existing Batch 10 evaluation modules used by
Step 7. Run Ruff, the Step 7 tests, all Portfolio tests and the complete repository suite in the
real
checkout before commit.

## Explicit Step 7 boundary

Step 7 completes the coordinated PAPER trading replay and Master trading evaluation foundation.

It does not yet seal a dedicated Batch 21e closure/audit artifact across the complete run, and it
does
not aggregate exact AI Gateway usage/economic-net evidence. Those can be added separately without
changing the single-capital execution model established here.
