# Batch 21d — Step 3 — Concurrent Arbitration Audit & Closure

Baseline: `8d0f8b3` — Deterministic Sequential Arbitrator.

## Goal

Seal one already-completed `MasterSequentialArbitrationResult` as immutable deterministic audit
evidence without replaying arbitration, mutating reservations, evaluating Risk again, submitting
broker orders, or providing LIVE authority.

The closure binds the exact arbitration policy, ordered batch, allocation policy, Master Risk Gate
policy, opening Master Portfolio snapshot, observed Master Portfolio snapshot, initial reservation
ledger, final reservation ledger, sequential result, every outcome fingerprint, and every embedded
Batch 21c Master Risk Gate closure fingerprint.

## Evidence and provenance checks

`build_master_arbitration_closure_seal()` rejects the closure when any of the following diverge:

- Master Portfolio identity;
- arbitration policy or batch provenance;
- allocation policy provenance;
- Master Risk Gate policy provenance;
- opening snapshot provenance;
- observed portfolio snapshot provenance;
- batch source ledger versus supplied initial ledger;
- sequential result initial/final ledger fingerprints;
- batch entry count, rank, system, proposal, reservation, or candidate fingerprint;
- final reservation state versus each `ADMIT` / `REJECT` outcome.

For `ADMIT`, the final reservation must be `COMMITTED` with `commit_ref == decision_id`.
For `REJECT`, the final reservation must be `RELEASED` with `release_ref == decision_id` and no
fabricated commit history.

## Mutation proof

The closure compares the complete initial and final reservation sets. Reservations outside the
batch must remain fingerprint-identical. The batch may not add or remove reservation records.

It also independently recomputes reservation-ledger accounting from the records for both endpoint
snapshots:

- reserved and committed Master capital;
- per-crew reserved/committed capital;
- per-crew reserved/committed open risk;
- per-crew reserved/committed gross exposure.

This prevents a forged aggregate snapshot from being accepted solely because it carries a valid
self-consistent SHA-256 payload.

## Closure contract

The step adds:

- `MasterArbitrationClosureStatus`;
- `MasterArbitrationClosureSeal`;
- `build_master_arbitration_closure_seal()`.

The seal stores admitted/rejected counts, the full ordered outcome fingerprint sequence, the full
ordered Master Risk Gate closure fingerprint sequence, and the sequential result fingerprint.
Its closure ID and closure fingerprint are deterministic.

## Authority invariants

This step is audit-only:

- `mutation_applied = False`;
- `reservation_mutation = False`;
- `risk_authority = False`;
- `admission_authority = False`;
- `local_risk_override = False`;
- `resize_authority = False`;
- `broker_authority = False`;
- `registry_mutation = False`;
- `live_authority = False`;
- `auto_execute = False`;
- `audit_only = True`.

The reservation mutations remain historical facts produced by Step 2 through the existing Batch
21c bridge. The closure does not apply or reverse them.

## Batch 21d status

With this step, Batch 21d has a complete V1 chain:

1. Step 1 — caller-supplied concurrent batch and deterministic FIFO ordering contracts;
2. Step 2 — sequential arbitration against the evolving reservation ledger;
3. Step 3 — immutable audit closure over the complete run.

No broker or LIVE integration is introduced by Batch 21d.

## Validation in generation harness

- `tests/portfolio/test_master_arbitration_closure.py`: 25 passed;
- all `tests/portfolio`: 299 passed;
- Python 3.13 compilation: passed;
- Python source line length <= 100: passed.

Ruff and the complete repository suite must still be run in the real checkout before commit.
