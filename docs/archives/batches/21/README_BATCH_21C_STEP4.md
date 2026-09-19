# Batch 21c — Step 4 — Master Risk Gate Audit & Closure

Baseline: `1649778` — Reservation-to-Admission Bridge.

## Goal

Seal one Master Risk Gate decision and its exact ledger outcome as immutable,
deterministic audit evidence. This step does not evaluate risk, mutate reservations,
submit orders, or provide any LIVE authority.

The closure binds:

- operator-owned `MasterRiskGatePolicy`;
- static `MasterAllocationPolicy` provenance;
- the exact local-Risk-bound `MasterRiskGateCandidate`;
- the exact `MasterPortfolioSnapshot` evaluated by the gate;
- the exact pre-transition `ReservationLedgerSnapshot`;
- the immutable `MasterRiskGateDecision`;
- the exact post-transition `ReservationLedgerSnapshot`;
- the `ReservationAdmissionReceipt` when a reservation transition exists;
- reservation closure seals for both the before and after ledger states.

## Supported closure shapes

### ADMIT

`RESERVED -> COMMITTED`

The post-transition reservation must carry `committed_at == decision.created_at` and
`commit_ref == decision.decision_id`. The receipt must bind exactly to the candidate,
decision, evaluated ledger, and resulting reservation.

### Master REJECT after local authorization

`RESERVED -> RELEASED`

The post-transition reservation must carry `released_at == decision.created_at` and
`release_ref == decision.decision_id`, with no fabricated commit history.

### Local Risk REJECTED

No reservation exists, therefore no Step 3 receipt exists. The closure accepts this case
only when the Master decision is `REJECT`, contains `LOCAL_RISK_NOT_AUTHORIZED`, and the
ledger is unchanged. No fake reservation or fake receipt is invented for audit symmetry.

## Mutation proof

For reservation-bound transitions the closure verifies that:

- the reservation set is unchanged;
- every non-target reservation fingerprint is unchanged;
- every non-target crew usage record is unchanged;
- the target crew aggregate delta is exactly the expected commit or release delta;
- Master capital capacity is unchanged;
- total reserved/committed/active/available capital changes exactly as required.

This prevents unrelated ledger mutations from being hidden inside an otherwise valid
admission receipt.

## Reused evidence

The builder reuses existing Batch 21b reconciliation and reservation closure contracts for
both the pre-transition and post-transition ledger snapshots. It does not re-read providers,
brokers, market data, or account state.

## Authority invariants

`MasterRiskGateClosureSeal` exposes only audit evidence:

- `mutation_applied = False`;
- `reservation_mutation = False`;
- `risk_authority = False`;
- `admission_authority = False`;
- `local_risk_override = False`;
- `resize_authority = False`;
- `broker_authority = False`;
- `registry_mutation = False`;
- `live_authority = False`;
- `auto_execute = False`.

The Master Risk Gate remains veto-only. Local Risk remains the trade-risk authority.

## Validation in generation harness

- `tests/portfolio/test_master_risk_gate_closure.py`: 24 passed;
- all `tests/portfolio`: 222 passed;
- Python 3.13 compilation: passed;
- Python source line length <= 100: passed.

Run Ruff and the full repository suite in the real checkout before commit.
