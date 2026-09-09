# Batch 21d — Step 2 — Deterministic Sequential Arbitrator

Baseline: `39e172b` — Concurrent Arbitration Contracts.

## Goal

Consume one immutable `MasterArbitrationBatch` in its sealed FIFO order and process every
candidate against the existing veto-only Master Risk Gate while the reservation ledger evolves
between entries.

The step reuses, without bypassing:

- `evaluate_master_risk_gate()` from Batch 21c Step 2;
- `apply_master_risk_gate_decision_to_reservation()` from Batch 21c Step 3;
- `build_master_risk_gate_closure_seal()` from Batch 21c Step 4.

It does not create a second Risk engine, resize local Risk-approved amounts, submit broker
orders, mutate the Agent Registry, or provide LIVE authority.

## Sequential flow

For every sealed batch entry:

1. snapshot the current reservation ledger;
2. evaluate the existing Master Risk Gate against that exact snapshot;
3. apply the decision through the existing Reservation-to-Admission Bridge;
4. snapshot the resulting ledger;
5. build the existing Master Risk Gate closure seal;
6. append one immutable arbitration outcome;
7. continue with the evolved ledger.

Therefore candidate `N+1` always sees the reservation state produced by candidate `N`.

## FIFO semantics

`FIFO_RESERVATION_REQUEST` remains an evaluation order, not an invented economic-priority
optimizer.

Still-pending candidates are not removed from the ledger while earlier candidates are evaluated.
Their `RESERVED` capacity remains visible to the existing Master Risk Gate until their own turn.
This preserves the reservation ledger as the physical accounting truth and keeps the Step 3
TOCTOU invariant intact.

As a consequence, V1 does not promise that the earliest request must be admitted. Example:
with two active risk reservations of `3` and a Master risk ceiling of `3`, the first evaluation
sees both claims, can be rejected and released, then the second evaluation sees the reduced
ledger and can be admitted. This behavior is deterministic and fail-closed; no hidden fairness
score or temporary capacity fiction is introduced.

## Preconditions before first mutation

The arbitrator fails before any transition when:

- the arbitration policy is not explicitly configured;
- the batch does not bind to that exact arbitration policy;
- Master Portfolio IDs disagree;
- allocation-policy provenance disagrees;
- the opening snapshot is not the ledger opening snapshot;
- the current ledger fingerprint is not the batch source-ledger fingerprint;
- the supplied candidate set does not match the batch exactly;
- an entry does not bind to the expected candidate/reservation;
- `evaluated_at` precedes batch creation;
- `evaluated_at` is later than the portfolio observation used for reconciliation.

A completed batch cannot simply be replayed on the already-mutated ledger because its source
fingerprint is stale.

## Writer serialization

This V1 is deterministic sequential orchestration, not a cross-thread transaction manager. The
caller must serialize writes to one `MasterReservationLedger` while an arbitration run is in
progress. Existing stale-source validation, Step 3 TOCTOU checks, and Step 4 closure validation
remain active, but no new rollback/locking abstraction is invented in this batch.

## Result contracts

The step adds:

- `MasterSequentialArbitrationStatus`;
- `MasterSequentialArbitrationOutcome`;
- `MasterSequentialArbitrationResult`;
- `arbitrate_master_batch_sequentially()`.

Each outcome seals:

- rank and proposal/reservation identity;
- candidate fingerprint;
- ledger fingerprint before evaluation;
- exact Master Risk Gate decision and reason codes;
- admission receipt fingerprint;
- Master Risk Gate closure fingerprint;
- ledger fingerprint after transition.

The final result seals the complete contiguous ledger chain from the batch source state to the
final state.

## Authority invariants

The run reports that reservation mutations were applied because it orchestrates existing
commit/release transitions:

- `mutation_applied = True`;
- `reservation_mutation = True`.

But the result and its outcomes have no independent authority:

- `risk_authority = False`;
- `admission_authority = False`;
- `local_risk_override = False`;
- `resize_authority = False`;
- `broker_authority = False`;
- `registry_mutation = False`;
- `live_authority = False`;
- `auto_execute = False`.

Admission authority remains solely in each existing `MasterRiskGateDecision`, and local trade
risk authority remains solely in the existing deterministic Risk Engine.

## Validation in generation harness

- `tests/portfolio/test_master_arbitration_sequential.py`: 26 passed;
- all `tests/portfolio`: 274 passed;
- Python 3.13 compilation: passed;
- Python source line length <= 100: passed.

Ruff and the complete repository test suite must still be run in the real checkout before commit.
