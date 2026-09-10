# Batch 21e — Step 4 — Historical Reservation & Arbitration Bridge

Baseline: `880e4d6` — Historical Master Decision Barrier / Pre-Execution Integration.

## Goal

Bridge the locally Risk-authorized historical candidate seeds produced by Step 3 into the existing
Master Portfolio reservation, Master Risk Gate and concurrent arbitration stack while stopping
strictly before PAPER broker execution or any LIVE path.

The bridge reuses, rather than replaces:

- the Batch 21b `MasterReservationLedger` and `ReservationRequest`;
- the Batch 21c `MasterRiskGateCandidate` builder and veto-only Master Risk Gate;
- the Batch 21c reservation admission transition bridge;
- the Batch 21c per-candidate Master Risk Gate closure;
- the Batch 21d arbitration batch and sequential arbitrator;
- the Batch 21d arbitration audit closure.

No new Risk Engine, reservation engine, arbitration algorithm, broker, or execution model is added.

## Explicit capital requirement

Step 3 deliberately did not infer reservation capital from approved notional. Step 4 preserves that
boundary through `MasterHistoricalCapitalRequirement`.

For every locally authorized `MasterHistoricalCandidateSeed`, the caller must supply exactly one
operator-owned capital requirement containing:

- the exact `system_id`;
- the exact `proposal_id`;
- a finite `capital_amount > 0`;
- optional operator provenance through `source_ref`.

The requirement exposes `inferred_from_notional = False`.

The bridge never treats approved notional as cash and never derives leverage or margin rules that do
not already exist in the project.

## Exact reservation request

For each candidate seed, the bridge builds an existing Batch 21b `ReservationRequest` with:

- `requested_at = decision_barrier.observed_at` exactly;
- `capital_amount` from the explicit capital requirement;
- `open_risk_amount` from local Risk's exact approved risk;
- `gross_exposure_amount` from local Risk's exact approved notional;
- `request_ref = proposal_id`.

The deterministic request ID binds the candidate seed, capital requirement and exact barrier time.

Requirements and seeds are matched one-to-one before any reservation attempt. Missing, extra or
duplicate requirements fail before ledger mutation.

## Reservation order and anti-double-spend

The caller does not define economic priority by input ordering.

Seeds are attempted in canonical `(system_id, proposal_id)` order. Every reservation request for one
historical decision barrier uses the same explicit CLOSE timestamp. The existing reservation ledger
therefore remains the authority for allocation ceilings and global Master capital anti-double-spend.

The bridge does not create temporary over-reservations and does not bypass a failed reservation.

A failed reservation is retained as an explicit `NOT_RESERVED` attempt with the exact existing Batch
21b reason codes. It never becomes a Master Risk Gate candidate and never enters arbitration.

## Candidate creation

Only successful `RESERVED` outcomes create an existing Batch 21c `MasterRiskGateCandidate`.

The candidate is built from `MasterHistoricalCandidateSeed.to_local_risk_decision()` and the exact
reservation ID. The bridge verifies that the Batch 21c local Risk decision fingerprint remains
identical to the fingerprint sealed by Step 3.

Local `APPROVED` and `RESIZED` statuses therefore remain unchanged. The Master layer cannot
resize or upgrade them.

## Concurrent Master arbitration

After every reservation attempt for the exact CLOSE barrier has completed, all successfully reserved
candidates are passed together as the explicit concurrent set to the existing Batch 21d arbitration
builder.

The existing operator-owned FIFO strategy remains unchanged. Because every new reservation in this
historical barrier has the same `requested_at`, the existing deterministic tie-breakers apply
without inventing a time window, score, expected return, PnL ranking, Kelly sizing, agent vote,
reputation weight or other priority mechanism.

The existing sequential arbitrator then evaluates each candidate through the existing veto-only
Master Risk Gate against the evolving reservation ledger:

- Master `ADMIT` transitions its reservation to `COMMITTED`;
- Master `REJECT` transitions its reservation to `RELEASED`;
- no admitted quantity, risk or notional may differ from local Risk.

The complete run is sealed with the existing Batch 21d `MasterArbitrationClosureSeal`.

## Historical chronology and no-lookahead

Step 4 binds the exact Step 1 plan, Step 2 timeline and Step 3 decision barrier.

The current Master Portfolio snapshot must be observed exactly at the historical decision barrier.
The opening snapshot may not postdate that barrier.

Before any mutation, the bridge rejects a reservation ledger containing a reservation request,
commit, or release timestamp in the future relative to the current historical barrier.

Reservation requests, arbitration batch creation and Master Risk Gate evaluation for new candidates
all use the exact decision-barrier timestamp.

## Result states

`MasterHistoricalReservationArbitrationResult` has three explicit outcomes:

- `NO_AUTHORIZED_CANDIDATES`: Step 3 produced no locally authorized seed; no ledger mutation;
- `NO_RESERVATIONS`: authorized seeds existed but every reservation attempt failed; no Master
  arbitration is run;
- `ARBITRATED`: at least one reservation succeeded and the existing 21c/21d admission path
  completed.

`NO_RESERVATIONS` reports reservation mutation because the Batch 21b ledger records idempotency
attempt state even when no reservation record is created. It reports no admission transition.

## Single Master capital truth

The reservation ledger's physical capital capacity must equal
`MasterHistoricalReplayPlan.master_initial_capital`, and the opening Master snapshot equity must
equal that same amount.

The bridge never reads or sums source branch broker equities. It preserves:

- `single_master_capital = True`;
- `sums_branch_equities = False`.

Source `BacktestRun.config.initial_balance` values remain historical branch provenance only.

## Authority invariants

Step 4 may mutate only the existing reservation ledger through its existing public transitions.
It has no independent Risk or execution authority:

- local Risk remains the trade-risk authority;
- Master Risk Gate remains veto-only;
- arbitration only orders/evaluates an explicit concurrent set;
- no order intent is created;
- no PAPER broker is called;
- no LIVE path is touched;
- no AgentRegistry or recruitment state is mutated;
- no automatic execution occurs.

## Contracts

Step 4 adds:

- `MasterHistoricalCapitalRequirementSource`;
- `MasterHistoricalCapitalRequirement`;
- `MasterHistoricalReservationAttemptStatus`;
- `MasterHistoricalReservationAttempt`;
- `MasterHistoricalReservationArbitrationStatus`;
- `MasterHistoricalReservationArbitrationResult`;
- `build_master_historical_capital_requirement()`;
- `bridge_master_historical_reservation_and_arbitration()`.

All new persisted contracts use deterministic SHA-256 fingerprints.

## Deliberate limitation / next step

Step 4 completes historical reservation and Master admission for one decision barrier, but it does
not execute the admitted trade.

The current `PaperBroker` remains intentionally single-system, while a Master replay needs one
physical capital/accounting truth across multiple crews. Sharing one existing single-system broker
across crew `system_id` values would violate its contract; executing separate crew brokers and then
summing their equities would violate the Master capital invariant.

The next step must therefore define a **Master historical PAPER execution and capital-accounting
bridge** for admitted reservations before an end-to-end multi-bar Master replay can be considered
correct. That layer must preserve existing deterministic execution assumptions and must reconcile
fills, positions, releases and realized PnL back into one Master capital truth without creating a
LIVE execution path.

## Validation in generation harness

- `tests/portfolio/test_master_historical_replay_reservation_arbitration.py`: 38 passed;
- all `tests/portfolio`: 439 passed;
- Python 3.13 compilation: passed;
- Python source line length <= 100: passed.

Ruff is not installed in the generation harness. Run Ruff and the complete repository suite in the
real checkout before commit.
