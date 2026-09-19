# Batch 21d — Step 1 — Concurrent Arbitration Contracts

Baseline: `814629c` — Master Risk Gate audit closure.

## Goal

Define the immutable, deterministic contracts used to order a caller-supplied set of
concurrent, locally Risk-authorized proposals before sequential Master Portfolio arbitration.

This step does not evaluate the Master Risk Gate, mutate reservations, submit orders, or provide
LIVE authority.

## Operator-owned ordering policy

`MasterArbitrationPolicy` introduces one deliberately narrow V1 strategy:

`FIFO_RESERVATION_REQUEST`

The strategy must be configured explicitly. There is no implicit default. A
`NOT_CONFIGURED` policy carries no strategy and requires an explicit reason code.

The policy is tied to one `MasterAllocationPolicy` fingerprint and has no adaptive ranking,
agent influence, Risk authority, admission authority, reservation mutation, broker authority,
registry mutation, or LIVE authority.

## No invented concurrency window

Step 1 does not invent a numeric rule such as "requests within N seconds are concurrent".
The caller supplies the candidate set explicitly. The batch builder validates and orders that
set only.

A one-candidate batch is valid so the contract does not invent an arbitrary minimum batch size.

## Deterministic FIFO order

Candidates are ordered by:

1. reservation `requested_at`;
2. `system_id`;
3. `proposal_id`;
4. `reservation_id`.

The last three keys are deterministic tie-breakers only. No reputation, confidence, PnL,
agent vote, expected return, Kelly sizing, or learned score participates in V1 ordering.

## Candidate eligibility

Every batch candidate must:

- already be locally authorized by the existing Risk Engine (`APPROVED` or `RESIZED`);
- belong to the same Master Portfolio as the arbitration policy;
- bind to a reservation present in the supplied ledger snapshot;
- have that reservation still in `RESERVED` state;
- match the reservation `system_id`, proposal reference, open-risk amount, and gross-exposure
  amount;
- have a reservation request timestamp not earlier than its local Risk decision;
- be unique by candidate fingerprint, reservation, and `(system_id, proposal_id)`.

Locally `REJECTED` candidates are terminal and are never admitted into the arbitration batch.

## Batch provenance

`MasterArbitrationBatch` seals:

- Master Portfolio ID;
- arbitration policy fingerprint;
- allocation policy fingerprint;
- exact source reservation-ledger snapshot fingerprint;
- explicit batch creation timestamp;
- ordered immutable entries;
- deterministic batch ID and SHA-256 fingerprint.

Each `MasterArbitrationEntry` seals its rank, system/proposal/reservation IDs, local Risk time,
reservation request time, candidate fingerprint, and reservation fingerprint.

The batch is read-only evidence. It does not mutate the source ledger.

## Next step

Step 2 will consume this ordered batch and evaluate candidates sequentially against the existing
veto-only Master Risk Gate using a deterministic evolving arbitration state. Step 2 must still
have no broker or LIVE authority and may never override local Risk.

## Validation in generation harness

- `tests/portfolio/test_master_arbitration_contracts.py`: 26 passed;
- all `tests/portfolio`: 248 passed;
- Python 3.13 compilation: passed;
- Python source line length <= 100: passed.

Run Ruff and the full repository suite in the real checkout before commit.
