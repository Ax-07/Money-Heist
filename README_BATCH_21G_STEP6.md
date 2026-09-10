# Batch 21g — Step 6 — Dynamic Allocation & LIVE Readiness Assessment + Batch Closure

Baseline: `9855c85` — Batch 21g Step 5 Policy Change Lifecycle Audit + Closure Seal.

## Goal

Close Batch 21g at the infrastructure level without pretending that automatic dynamic allocation or
multi-crew LIVE is ready.

The Step 6 path is intentionally read-only:

`Step 5 SEALED policy-change lifecycle -> explicit operational evidence inventory -> deterministic
readiness assessment -> SEALED Batch 21g closure`.

The Step 6 reference result preserves three separate conclusions:

- Batch 21g infrastructure: `COMPLETE`;
- automatic dynamic allocation: `DISABLED`;
- multi-crew LIVE readiness: `BLOCKED`.

Closing the batch therefore does not arm LIVE, enable recurring reallocation, or certify production
readiness.

## Why LIVE readiness remains blocked

The current Batch 15 LIVE boundary is intentionally limited to the initial single LIVE system
`balanced_v1` and requires its own `LivePreflight` followed by an exact human operator arm.

Batch 21g must not reuse its own allocation-policy authorization as LIVE authorization.

Step 6 therefore preserves an unconditional structural blocker:

`BATCH15_LIVE_BOUNDARY_SINGLE_SYSTEM_ONLY`.

Even a future stronger policy store and complete OOS/PAPER/SHADOW evidence cannot make this Step 6
contract report multi-crew LIVE ready. A future batch must explicitly extend the LIVE boundary while
preserving the existing fail-closed operator arm.

## Current policy-store scope

The Step 5 closure carries the actual store capability evidence established by Step 4.

With the current SQLite reference adapter:

- `durable = True`;
- `multi_process_safe = True` for processes sharing the same supported local file;
- `multi_host_safe = False`;
- `live_ready = False`.

Step 6 therefore also reports:

- `POLICY_STORE_NOT_MULTI_HOST_SAFE`;
- `POLICY_STORE_NOT_LIVE_READY`.

Those reasons disappear if a future Step 5-compatible closure comes from a store that truthfully
advertises stronger capabilities, but the Batch 15 single-system blocker remains.

## Explicit operational evidence inventory

Step 6 introduces explicit immutable evidence references for four operational categories:

- `HISTORICAL_OOS`;
- `WALK_FORWARD_OOS`;
- `PAPER`;
- `SHADOW`.

Each category must be represented exactly once. The caller cannot omit a category silently.

Evidence status is one of:

- `AVAILABLE`;
- `BLOCKED`;
- `NOT_PROVIDED`.

`AVAILABLE` means only that an external artifact reference and SHA-256 fingerprint were supplied. It
is not an automatic quality verdict and Step 6 does not inspect or reinterpret trading performance.

`BLOCKED` requires explicit artifact provenance plus a reason code.

`NOT_PROVIDED` requires an explicit reason code and cannot carry fake artifact provenance.

Unavailable evidence adds deterministic readiness blockers. Step 6 never invents a positive OOS,
walk-forward, PAPER, or SHADOW result.

## No invented acceptance thresholds

Step 6 does not invent:

- minimum Sharpe or Sortino;
- maximum drawdown thresholds;
- minimum win rate;
- minimum number of trades;
- minimum PAPER duration;
- minimum SHADOW duration;
- economic-lift thresholds;
- allocation percentages;
- Kelly sizing;
- statistical correlation limits.

If production acceptance criteria are not already explicit in operator-owned evidence, they remain
outside this contract.

## Step 5 closure is the authority for the completed mutation lifecycle

`assess_master_allocation_live_readiness()` requires an intact
`MasterAllocationPolicyChangeClosureSeal` from Step 5.

It verifies:

- the Step 5 closure SHA-256 fingerprint;
- `status = SEALED`;
- `lifecycle_closed = True`;
- `dynamic_allocation_enabled = False`;
- absence of policy mutation, reservation, Risk, admission, registry, broker, or LIVE authority.

Step 6 does not reopen the SQLite store, perform a new CAS, or replay Step 1-4.

The Step 5 seal is already the read-only proof that the exact persistent post-attempt policy was
verified before closure.

## Readiness assessment

`MasterAllocationReadinessAssessment` records:

- Master Portfolio identity;
- Step 5 closure fingerprint;
- active static allocation-policy identity and fingerprint;
- exact Step 5 store capability flags;
- the four explicit evidence fingerprints;
- deterministic blocker codes;
- explicit timezone-aware `assessed_at`;
- preservation of Batch 15 preflight and operator arm boundaries.

The assessment is immutable and SHA-256 fingerprinted.

Its fixed infrastructure/runtime conclusions in this version are:

- `infrastructure_status = COMPLETE`;
- `dynamic_allocation_status = DISABLED`;
- `multi_crew_live_readiness_status = BLOCKED`.

This is intentional. Step 6 is a truthful assessment of the current architecture, not a mechanism for
forcing a green status.

## Automatic dynamic allocation remains disabled

Step 6 closes the operator-gated static policy-change infrastructure delivered in 21g.

It does not introduce:

- a scheduler;
- recurring Master Professor invocation;
- auto-acceptance of recommendations;
- auto-authorization;
- automatic CAS application;
- adaptive allocation percentages;
- autonomous capital transfer.

The Master Professor remains advisory. Every real static policy change still follows the explicit
human-gated chain introduced in Steps 1-5.

## Existing LIVE gates remain separate

Step 6 explicitly records:

- `batch15_live_preflight_preserved = True`;
- `operator_arm_still_required = True`;
- `no_live_activation_performed = True`.

No Step 21g object can replace:

- Batch 15 `LivePreflight`;
- the exact operator confirmation required by `LiveActivationController`;
- the existing LIVE execution service's durable authorization checks.

A READY single-system Batch 15 report, if one exists later, must not be interpreted as multi-crew LIVE
readiness.

## Risk and execution boundaries

Step 6 does not:

- approve a trade rejected by local deterministic Risk;
- override or loosen the Master Risk Gate;
- resize a Risk-authorized proposal;
- reserve, commit, or release capital;
- mutate `AgentRegistry`;
- submit PAPER orders;
- mutate broker positions;
- arm LIVE;
- submit LIVE orders.

The local Risk Engine remains the trade-level authority and the Master Risk Gate remains veto-only.

## One physical Master capital

Step 6 does not calculate, aggregate, or clone capital.

It does not sum SHADOW equities and does not create per-crew cash balances.

Crew envelopes remain ceilings over one physical Master capital truth.

## Batch 21g closure seal

`seal_master_allocation_batch21g()` accepts only an intact readiness assessment and produces
`MasterAllocationBatch21gClosureSeal`.

The seal records:

- `status = SEALED`;
- `batch_21g_complete = True`;
- exact readiness-assessment fingerprint;
- exact Step 5 closure fingerprint;
- `infrastructure_status = COMPLETE`;
- `dynamic_allocation_status = DISABLED`;
- `multi_crew_live_readiness_status = BLOCKED`;
- the exact blocker set;
- `sealed_at = assessment.assessed_at`.

The seal adds no wall clock and performs no state access.

`batch_21g_complete = True` means the scoped Batch 21g infrastructure is closed. It does not mean that
LIVE can be armed.

## Determinism

Step 6 introduces no random source and no internal wall clock.

For identical Step 5 closure, identical explicit evidence inventory, and identical `assessed_at`, the
assessment and final closure IDs/fingerprints are identical.

Evidence ordering is canonicalized by evidence kind.

Blocker codes are sorted and unique.

## No AI call

Step 6 performs no AI work.

It does not call:

- an AI provider;
- `AIGateway.generate_structured()`;
- `AIGatewayRequest`;
- the Master Professor.

## Contracts

Step 6 adds:

- `MasterAllocationReadinessEvidenceKind`;
- `MasterAllocationReadinessEvidenceStatus`;
- `MasterAllocationReadinessEvidence`;
- `MasterAllocationInfrastructureStatus`;
- `MasterAllocationDynamicStatus`;
- `MasterAllocationMultiCrewLiveReadinessStatus`;
- `MasterAllocationReadinessReasonCode`;
- `MasterAllocationReadinessAssessment`;
- `MasterAllocationBatch21gClosureStatus`;
- `MasterAllocationBatch21gClosureSeal`;
- `build_master_allocation_readiness_evidence()`;
- `assess_master_allocation_live_readiness()`;
- `seal_master_allocation_batch21g()`;
- deterministic payload helpers.

## Explicit Step 6 boundary

Step 6 does not:

- make SQLite multi-host-safe;
- make the policy store LIVE-ready;
- extend the Batch 15 preflight to multiple crews;
- arm LIVE;
- execute a LIVE order;
- enable automatic dynamic allocation;
- schedule policy changes;
- mutate policy state;
- run compare-and-swap;
- reserve capital;
- call Risk;
- call a broker;
- call AI;
- invent missing operational evidence or thresholds.

Any later multi-crew LIVE work must be a new explicit boundary and must preserve the Batch 14/15
fail-closed execution and human-arm contracts.

## Validation in reconstruction harness

Validation performed for the new code:

- Batch 21g Step 6 targeted tests: 30 passed;
- cumulative Batch 21f Steps 1-4 + Batch 21g Steps 1-6 targeted tests: 276 passed;
- Python compilation: passed;
- public `app.portfolio` import: passed;
- `app.evaluation` implicit import from `app.portfolio`: absent;
- `app.trading.live.preflight` implicit import from `app.portfolio`: absent;
- Python source/test line length <= 100: passed.

The reconstruction harness still contains older compatibility stubs. Its Step 5 baseline produced
`245 failed / 562 passed` in the complete `tests/portfolio` run. With Step 6 applied it produces the
same 245 pre-existing failures and `592 passed`, exactly 30 additional passing tests.

The real repository checkout remains authoritative for Ruff, all Portfolio tests, and the complete
repository suite before commit.
