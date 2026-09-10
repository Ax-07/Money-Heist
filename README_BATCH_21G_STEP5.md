# Batch 21g — Step 5 — Policy Change Lifecycle Audit + Closure Seal

Baseline: `517ea53` — Batch 21g Step 4 Durable Policy Store + Persistent CAS.

## Goal

Close one complete Batch 21g allocation-policy change attempt with deterministic,
read-only audit evidence and an immutable closure seal.

The Step 5 path is intentionally limited to:

`Step 1 change candidate -> Step 2 operator authorization -> Step 2 preflight ->
Step 3 replacement receipt -> Step 4 durable store snapshot -> VERIFIED audit -> SEALED closure`.

Step 5 never mutates the allocation policy and never invokes compare-and-swap.

## Why this step exists

Step 3 introduced the first real static `MasterAllocationPolicy` replacement and produced an
immutable replacement receipt. Step 4 then added durable same-file SQLite persistence and a public
CAS store port.

A replacement receipt alone is still only evidence of the mutation attempt. Step 5 verifies that the
complete authorization chain is intact and that the durable store still contains exactly the
post-attempt policy represented by that receipt before declaring the lifecycle closed.

## Outcomes that can be closed

Step 5 accepts the two legitimate Step 3 terminal outcomes:

- `APPLIED`;
- `CAS_CONFLICT`.

Both can be audited and sealed because both are meaningful terminal outcomes.

For `APPLIED`, Step 5 requires the durable store to contain exactly the requested replacement policy.

For `CAS_CONFLICT`, Step 5 requires the durable store to still contain exactly the policy observed by
the failed compare-and-swap attempt. The receipt must record
`policy_mutation_performed = False`.

A store that changed again after the receipt cannot be sealed against that stale post-attempt state.

## Complete provenance verification

`audit_master_allocation_policy_change()` re-hashes and validates:

- the Step 1 `MasterAllocationPolicyChangeCandidate`;
- the Step 2 application authorization;
- the Step 2 deterministic preflight;
- the original base `MasterAllocationPolicy`;
- the Step 3 `MasterAllocationPolicyReplacementReceipt`;
- the current policy read from the Step 4 durable store.

It verifies exact IDs and fingerprints across every edge of the chain.

The authorization must still be exactly `AUTHORIZE / AUTHORIZED`.

The preflight must still be exactly `READY_FOR_APPLICATION`, with only the `READY` reason and every
verification flag true.

## Rebuilding the requested replacement

Step 5 does not trust only the replacement fingerprint stored in the Step 3 receipt.

It deterministically rebuilds the expected replacement policy with the existing
`build_master_allocation_policy()` function from:

- the exact Master Portfolio ID;
- the exact requested new policy ID;
- the exact base membership;
- the exact operator-owned envelopes carried by the Step 1 candidate;
- the exact application source reference carried by the Step 3 receipt.

The rebuilt fingerprint must equal the requested replacement fingerprint in the receipt.

This proves that no new allocation values were introduced between advisory review and application.

## Durable store requirement

A Step 5 closure requires a store that declares:

- `durable = True`;
- `multi_process_safe = True`.

The current `SQLiteMasterAllocationPolicyStore` satisfies those guarantees for processes sharing one
supported local SQLite database file.

The in-memory Step 3 holder cannot produce a Step 5 durable lifecycle closure.

The audit records the store capability evidence explicitly:

- `store_durable`;
- `store_multi_process_safe`;
- `store_multi_host_safe`;
- `store_live_ready`.

Step 5 does not upgrade or reinterpret those capabilities.

With the current SQLite adapter, `store_multi_host_safe` and `store_live_ready` remain false.

## Explicit store identity

The caller supplies an explicit nonblank `store_ref`.

Step 5 does not invent, infer, normalize or auto-discover a production database path or deployment
identity.

The store reference is audit provenance only. It grants no runtime authority.

## Read-only audit

`audit_master_allocation_policy_change()` performs exactly one state operation on the store:

`snapshot()`.

It does not call:

- `compare_and_swap()`;
- policy replacement;
- reservation operations;
- local Risk;
- the Master Risk Gate;
- a broker;
- PAPER execution;
- LIVE execution;
- AI.

The audit itself exposes no policy mutation authority.

## Audit report

A successful audit returns `MasterAllocationPolicyChangeAuditReport` with:

- `status = VERIFIED`;
- complete Step 1-4 fingerprints;
- the terminal replacement status and reason;
- base policy identity and fingerprint;
- requested replacement identity and fingerprint;
- durable active policy identity and fingerprint;
- explicit store capability evidence;
- explicit `audited_at` timestamp;
- deterministic verification flags.

All verification flags must be true for the dataclass to validate.

The report is immutable and SHA-256 fingerprinted.

## Closure seal

`seal_master_allocation_policy_change()` accepts only an intact `VERIFIED` audit.

It creates `MasterAllocationPolicyChangeClosureSeal` with:

- `status = SEALED`;
- the exact audit fingerprint;
- the exact Step 3 replacement receipt fingerprint;
- the exact terminal outcome;
- the exact active durable policy identity and fingerprint;
- the exact store reference and capability evidence;
- `sealed_at = audit.audited_at`.

The seal does not read the store again and does not generate a wall-clock timestamp.

## Determinism

Step 5 introduces no random source and no internal wall clock.

The caller provides the timezone-aware `audited_at` timestamp.

For identical source objects, identical durable state, identical `store_ref` and identical timestamp,
the audit and closure IDs/fingerprints are identical.

## No autonomous dynamic allocation

Step 5 closes a static operator-authorized policy-change attempt.

It does not enable:

- recurring allocation changes;
- scheduled reallocation;
- automatic promotion of Master Professor recommendations;
- allocation optimization;
- Kelly sizing;
- inferred correlation matrices;
- invented thresholds or scores.

Both audit and closure expose `dynamic_allocation_enabled = False`.

## Risk and trading boundaries

Step 5 does not grant authority to:

- override local deterministic Risk;
- loosen Master Risk Gate constraints;
- resize a Risk-authorized proposal;
- reserve, commit or release capital;
- mutate `AgentRegistry`;
- submit PAPER orders;
- mutate broker positions;
- arm LIVE;
- submit LIVE orders.

The local Risk Engine remains the trade-level risk authority and the Master Risk Gate remains
veto-only.

## One physical Master capital

Step 5 audits allocation-policy ceilings only.

It does not sum SHADOW equities, create crew cash accounts or infer Master capital from branch
backtests.

Crew allocation envelopes remain ceilings over one physical Master capital truth.

## Store changes after receipt fail closed

The durable snapshot is deliberately checked at audit time.

If an `APPLIED` receipt says policy `P2` became active but the store now contains `P3`, the audit fails.

If a `CAS_CONFLICT` receipt says policy `P2` was observed and left active but the store now contains
`P3`, the audit also fails.

A later policy state needs its own lifecycle evidence. Step 5 never seals stale state as if it were
current.

## Contracts

Step 5 adds:

- `MasterAllocationPolicyChangeAuditStatus`;
- `MasterAllocationPolicyChangeAuditReport`;
- `MasterAllocationPolicyChangeClosureStatus`;
- `MasterAllocationPolicyChangeClosureSeal`;
- `audit_master_allocation_policy_change()`;
- `seal_master_allocation_policy_change()`;
- deterministic payload helpers for audit and closure fingerprints.

## Explicit Step 5 boundary

Step 5 does not:

- mutate `MasterAllocationPolicy`;
- perform compare-and-swap;
- persist new policy state;
- create a distributed lock;
- claim multi-host safety;
- claim LIVE readiness;
- enable automatic dynamic allocation;
- generate allocation values;
- call AI;
- call Risk or admission;
- reserve capital;
- execute PAPER or LIVE.

Any future LIVE-readiness work must preserve the operator authorization, stale-write protection,
durable-state integrity, Risk authority and fail-closed boundaries established in Batch 21g.

## Validation in reconstruction harness

Validation performed for the new code:

- Batch 21g Step 5 targeted tests: 29 passed;
- Batch 21g Step 3-5 regression tests: 84 passed;
- cumulative Batch 21f Steps 1-4 + Batch 21g Steps 1-5 targeted tests: 246 passed;
- Python compilation: passed;
- public `app.portfolio` import: passed;
- `app.evaluation` implicit import from `app.portfolio`: absent;
- Python source/test line length <= 100: passed.

The reconstruction harness still contains older compatibility stubs. Its unchanged Step 4 baseline
produces `245 failed / 533 passed` in the complete `tests/portfolio` run. With Step 5 applied it
produces the same 245 pre-existing failures and `562 passed`, exactly 29 additional passing tests.

The real repository checkout remains authoritative for Ruff, all Portfolio tests and the complete
repository suite before commit.
