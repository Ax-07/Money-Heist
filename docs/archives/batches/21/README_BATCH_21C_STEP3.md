# Batch 21c — Step 3 — Reservation-to-Admission Bridge

Baseline: `c94f15e` — deterministic veto-only Master Risk Gate evaluator.

## Goal

Bind one immutable `MasterRiskGateDecision` to the reservation it evaluated and apply exactly
one reservation lifecycle transition:

- `ADMIT` -> `RESERVED` becomes `COMMITTED`;
- `REJECT` -> `RESERVED` becomes `RELEASED`.

The bridge does not evaluate risk, resize amounts, submit orders, mutate the agent registry, or
provide any LIVE authority.

## Contracts

The step adds:

- `ReservationAdmissionTransitionStatus`;
- `ReservationAdmissionReasonCode`;
- `ReservationAdmissionBridgeError`;
- `ReservationAdmissionReceipt`;
- `apply_master_risk_gate_decision_to_reservation()`.

Every successful transition produces an immutable deterministic receipt sealed by SHA-256.
Transition time and reference are derived from the already-sealed Master gate decision, so an
exact retry yields the same receipt.

## Binding checks

Before any first transition the bridge verifies:

- decision fingerprint binds to the supplied candidate;
- candidate Master Portfolio matches the ledger;
- a reservation ID is present and exists;
- reservation membership, proposal reference, policy provenance, opening snapshot provenance,
  open-risk amount, and gross-exposure amount match the candidate;
- the gate decision does not precede the reservation request;
- the reservation is still `RESERVED` unless this is an exact retry.

A mismatched reservation is never released automatically because it could belong to another
proposal.

## TOCTOU rule

For a first `ADMIT`, the current ledger fingerprint must exactly match the ledger fingerprint
used by the Master gate evaluation. Any intervening ledger change fails closed with
`STALE_LEDGER_SNAPSHOT`.

For a `REJECT`, unrelated later ledger changes do not prevent releasing the still-bound
`RESERVED` reservation. Release only reduces active commitments and therefore cannot loosen
risk limits.

## State conflicts

The bridge does not reverse unrelated lifecycle history:

- an already `COMMITTED` reservation cannot be claimed by another ADMIT;
- a `REJECT` cannot release an already `COMMITTED` reservation through this bridge;
- an already `RELEASED` reservation cannot be committed by a late ADMIT.

Exact retries with the same decision metadata are accepted idempotently.

## Authority invariants

`ReservationAdmissionReceipt` exposes:

- `risk_authority = False`;
- `admission_authority = False` — admission authority remains in `MasterRiskGateDecision`;
- `local_risk_override = False`;
- `resize_authority = False`;
- `broker_authority = False`;
- `registry_mutation = False`;
- `live_authority = False`;
- `auto_execute = False`;
- `reservation_transition = True`.

This step is not a broker bridge and does not modify PAPER or LIVE execution paths.

## Validation in generation harness

- `tests/portfolio/test_master_risk_gate_admission.py`: 22 passed;
- all `tests/portfolio`: 198 passed;
- Python 3.13 compilation: passed;
- Python source line length <= 100: passed.

Run Ruff and the full repository suite in the real checkout before commit.
