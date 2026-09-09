# Batch 21b — Step 4: Reservation Audit & Closure

Baseline expected: `52ef643` (`feat(portfolio): add reservation reconciliation bridge`).

## Scope

This step adds a deterministic, immutable audit seal over the evidence already produced by
Batch 21a and Batch 21b Steps 1–3. It does not re-read providers and does not mutate policy,
reservations, reconciliation state, Risk, brokers, AgentRegistry, Task Force, or LIVE state.

The closure seal explicitly binds:

- the current static allocation policy and its operator provenance;
- the opening Master Portfolio snapshot and its 21a provenance audit seal;
- the current Master Portfolio snapshot and its 21a provenance audit seal;
- the Reservation Ledger snapshot;
- the Reservation Reconciliation report;
- every persisted reservation record and its final lifecycle path;
- the final reconciliation status and reason codes;
- one deterministic SHA-256 closure fingerprint.

## Lifecycle audit

For each persisted reservation the closure records one canonical path:

- `RESERVED`;
- `RESERVED -> COMMITTED`;
- `RESERVED -> RELEASED`;
- `RESERVED -> COMMITTED -> RELEASED`.

The path is derived only from the immutable reservation record metadata already present in the
ledger snapshot. Step 4 does not invent an event journal. In particular, failed reservation
attempts are not turned into lifecycle records because the Step 2 ledger snapshot does not
persist an attempt-history journal.

## Fail-closed provenance

The builder rejects evidence that cannot be cryptographically linked, including a wrong opening
snapshot, a reconciliation report built from another policy, another ledger snapshot, or another
current portfolio snapshot. Reservation records must also remain scoped to the Master Portfolio,
policy fingerprint, and opening snapshot carried by their ledger snapshot.

A reconciliation that is legitimately `PENDING`, `INCONSISTENT`, or `UNAVAILABLE` can still be
sealed as evidence. The seal preserves that status and its reason codes; it never upgrades it to
`CONSISTENT` and never applies a mutation.

The seal exposes the policy fingerprint used for reconciliation separately from the policy
fingerprint embedded in the ledger, so a policy mismatch remains visible and auditable.

## Non-authority invariants

The closure has no allocation mutation, reservation mutation, Risk authority, admission authority,
broker authority, AgentRegistry mutation, or LIVE authority.

## Validation target

Run:

```powershell
uv run ruff check app/portfolio tests/portfolio/test_master_reservation_closure.py
uv run pytest -q tests/portfolio/test_master_reservation_closure.py
uv run pytest -q tests/portfolio
uv run pytest -q
```
