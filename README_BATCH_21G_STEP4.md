# Batch 21g — Step 4 — Durable Policy Store Port + Persistent CAS Contract

Baseline: `6b6f4d0` — Batch 21g Step 3 Atomic Policy Replacement + Audit Receipt.

## Goal

Replace the Step 3 concrete in-memory state dependency with a narrow atomic-store port, then add a
durable SQLite reference adapter that preserves the exact Step 3 compare-and-swap semantics.

The Step 4 path is intentionally limited to:

`existing 21g application chain -> MasterAllocationPolicyAtomicStore -> mutation-time CAS -> existing
APPLIED / CAS_CONFLICT receipt`.

Step 4 does not change the operator authorization chain, generate allocation values, reserve capital,
call Risk, execute PAPER, arm LIVE, or enable automatic dynamic allocation.

## Why this step exists

Batch 21g Step 3 proved the correct mutation boundary using
`InMemoryMasterAllocationPolicyAtomicState`, but that holder explicitly declared:

- `durable = False`;
- `multi_process_safe = False`;
- `live_ready = False`.

That implementation is useful for deterministic tests and one-process PAPER/SHADOW flows, but it is
not sufficient as persistent configuration state.

Step 4 therefore extracts the smallest storage contract needed by the already-existing Step 3
application function instead of creating a second allocation engine.

## Atomic store port

`MasterAllocationPolicyAtomicStore` defines only the state behavior required by Step 3:

- `snapshot()` returns the integrity-validated active `MasterAllocationPolicy`;
- `compare_and_swap()` compares exact Master Portfolio ID, policy ID and SHA-256 fingerprint, then
  replaces the policy atomically or returns the policy observed at the mutation boundary.

The public `MasterAllocationPolicyAtomicSwapOutcome` carries:

- `swapped`;
- `observed_policy`;
- `active_policy`.

`apply_master_allocation_policy_replacement()` now accepts this port rather than the concrete in-memory
holder. Its authorization, preflight, policy construction and audit-receipt semantics remain unchanged.

## In-memory compatibility

`InMemoryMasterAllocationPolicyAtomicState` remains available and implements the new port.

Its scope remains explicitly limited:

- `in_process_only = True`;
- `durable = False`;
- `multi_process_safe = False`;
- `multi_host_safe = False`;
- `live_ready = False`.

All Batch 21g Step 3 tests remain valid through the new interface.

## SQLite durable reference adapter

Step 4 adds `SQLiteMasterAllocationPolicyStore` using Python's standard-library `sqlite3` module.

The adapter is bound to:

- one explicit operator-owned database path;
- one explicit `master_portfolio_id`.

It stores one active allocation-policy row per Master Portfolio.

No external dependency is added.

## Bootstrap behavior

An `initial_policy` may be supplied when the adapter is created.

If the Master Portfolio row does not yet exist, the policy is inserted transactionally.

If the row already exists with the exact same policy, bootstrap is idempotent.

If the row already exists with a different policy, initialization fails closed. Existing persistent
state is never silently overwritten by constructor/bootstrap behavior.

The adapter can later be reopened without supplying `initial_policy`; `snapshot()` then reads the
persisted active policy.

## Persistent representation and integrity

The SQLite row stores:

- Master Portfolio ID;
- active policy ID;
- active policy fingerprint;
- canonical storage JSON for members, envelopes, exact decimal text, policy metadata and fingerprint.

Every read reconstructs the real immutable `MasterAllocationPolicy` contracts and revalidates their
existing SHA-256 fingerprint.

The row-level policy ID/fingerprint metadata must also exactly match the reconstructed policy.

Corrupted JSON, malformed records, invalid decimal data, fingerprint tampering or metadata mismatch
therefore fail closed before the policy can be used.

## Persistent mutation-time CAS

`SQLiteMasterAllocationPolicyStore.compare_and_swap()` opens a database transaction with
`BEGIN IMMEDIATE` before reading the active row.

While that transaction owns the SQLite write lock, it:

1. reads and integrity-validates the active policy;
2. compares the exact expected Master Portfolio ID, policy ID and fingerprint;
3. rejects membership changes;
4. updates only the row matching the expected policy ID and fingerprint;
5. commits the replacement.

If the expected base policy is stale, no update occurs and the existing Step 3 path returns
`CAS_CONFLICT`.

The adapter sets `PRAGMA synchronous = FULL` on its connections so committed local-file transactions
use SQLite's strongest standard synchronous setting.

## Concurrency semantics

The persistent adapter opens independent SQLite connections for operations rather than sharing one
Python connection object.

The Step 4 tests create two independent adapter instances against the same database file and perform
concurrent replacement attempts from the same base fingerprint.

Exactly one attempt becomes `APPLIED`; the other observes the newly committed policy and becomes
`CAS_CONFLICT`.

This is the persistent equivalent of the Step 3 two-writer invariant.

## Durability and deployment scope

The SQLite reference adapter declares:

- `in_process_only = False`;
- `durable = True`;
- `multi_process_safe = True` for processes using the same supported local SQLite database file;
- `multi_host_safe = False`;
- `live_ready = False`.

The adapter is intentionally not claimed to be a distributed lock, replicated configuration service,
or multi-host consensus mechanism.

Step 4 therefore improves persistence and same-file process safety without prematurely declaring the
allocation layer LIVE-ready.

A future production adapter can implement the same narrow port using a deployment-appropriate
transactional datastore without changing the Step 1–3 authorization semantics.

## Static replacement remains the only mutation

The persistent store does not create an autonomous allocator.

The replacement policy is still built by the existing Step 3 function from the exact operator-owned
candidate envelopes. Every change still requires the complete chain:

`sealed SHADOW advisory -> change candidate -> second operator AUTHORIZE -> READY preflight ->
mutation-time CAS -> receipt`.

No scheduler, optimizer or recurring policy change loop is introduced.

## Risk and execution boundary

Step 4 does not:

- approve a trade rejected by local deterministic Risk;
- override the Master Risk Gate;
- reserve, commit or release Master capital;
- resize a Risk-authorized proposal;
- mutate `AgentRegistry`;
- submit PAPER orders;
- mutate broker positions;
- arm LIVE;
- submit LIVE orders.

`SQLiteMasterAllocationPolicyStore` exposes no Risk, broker or execution methods and declares no LIVE
readiness.

The local Risk Engine remains the trade-level risk authority and the Master Risk Gate remains veto-only.

## One physical Master capital

Step 4 persists allocation ceilings only.

It does not persist or aggregate SHADOW equities as capital, create per-crew cash balances, or clone
Master capital. Crew envelopes remain ceilings over one physical Master-capital truth.

## No AI call

Step 4 performs no AI work.

It does not call an AI provider, `AIGateway.generate_structured()`, `AIGatewayRequest`, or the Master
Professor. The Master Professor reasoning remains sealed in Batch 21f.

## Contracts

Step 4 adds:

- `MasterAllocationPolicyAtomicStore`;
- `MasterAllocationPolicyAtomicSwapOutcome`;
- `SQLiteMasterAllocationPolicyStore`.

It also refactors `InMemoryMasterAllocationPolicyAtomicState` and
`apply_master_allocation_policy_replacement()` to use the new public store port without changing Step 3
business semantics.

## Explicit Step 4 boundary

Step 4 does not:

- claim distributed or multi-host atomicity;
- provide replication or failover;
- define secrets/backup/restore operations;
- auto-select a database path;
- enable automatic or scheduled allocation changes;
- generate allocation numbers;
- change Portfolio membership;
- call Risk or the Master Risk Gate;
- execute PAPER;
- arm or execute LIVE;
- call AI.

A later Batch 21g step should close the policy-change lifecycle with an explicit integrity/audit seal
and readiness report before considering any broader dynamic-allocation or LIVE-readiness work.

## Validation in reconstruction harness

Validation performed for the new code:

- Batch 21g Step 4 targeted tests: 27 passed;
- Batch 21g Step 3 regression tests after port refactor: 28 passed;
- cumulative Batch 21f Steps 1–4 + Batch 21g Steps 1–4 targeted tests: 217 passed;
- persistent two-store concurrent CAS test: exactly one `APPLIED`, one `CAS_CONFLICT`;
- persisted policy survives adapter reopen;
- corrupted storage records fail closed;
- Python compilation: passed;
- public `app.portfolio` import: passed;
- `app.evaluation` implicit import from `app.portfolio`: absent;
- Python source/test line length <= 100: passed.

The reconstruction harness is not the authoritative full repository checkout. Run Ruff, the targeted
Step 4 tests, all Portfolio tests and the complete repository suite in the real checkout before commit.
