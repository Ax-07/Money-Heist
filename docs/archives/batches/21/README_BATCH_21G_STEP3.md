# Batch 21g — Step 3 — Atomic Policy Replacement + Audit Receipt

Baseline: `3a1e2fc` — Batch 21g Step 2 Explicit Policy Application Authorization + Deterministic Preflight.

## Goal

Introduce the first real `MasterAllocationPolicy` mutation in Batch 21, but only through a narrow,
mutation-time compare-and-swap boundary.

The Step 3 path is intentionally limited to:

`21g Step 1 change candidate -> 21g Step 2 AUTHORIZE -> READY_FOR_APPLICATION preflight -> atomic
base-policy revalidation -> APPLIED / CAS_CONFLICT -> immutable audit receipt`.

A successful Step 3 changes only the active static allocation policy held by the Step 3 atomic state.
It does not reserve capital, call Risk, execute PAPER, arm LIVE, or enable automatic dynamic allocation.

## Why Step 2 preflight is not enough

Batch 21g Step 2 deliberately records:

- `preflight_only = True`;
- `atomic_compare_and_swap_still_required = True`;
- `policy_application_performed = False`.

A `READY_FOR_APPLICATION` result therefore describes the base policy observed at `checked_at`, but it
cannot guarantee that the policy remains unchanged a moment later.

Step 3 closes that TOCTOU gap by checking the exact Master Portfolio ID, base policy ID, and base
policy fingerprint inside the same lock that performs the replacement.

If any of those values changed after preflight, the mutation does not happen.

## Exact application eligibility

`apply_master_allocation_policy_replacement()` accepts only an intact chain where:

- the Step 1 change candidate fingerprint is valid;
- the candidate remains `READY_FOR_OPERATOR_AUTHORIZATION`;
- the Step 2 authorization fingerprint is valid;
- the operator action is exactly `AUTHORIZE`;
- the authorization status is exactly `AUTHORIZED`;
- the Step 2 preflight fingerprint is valid;
- the preflight status is exactly `READY_FOR_APPLICATION`;
- the preflight carries only the `READY` reason;
- every Step 2 verification flag is true;
- the supplied base `MasterAllocationPolicy` fingerprint is valid;
- the base policy remains `CONFIGURED`;
- candidate, authorization, preflight, and base policy preserve exact provenance;
- the candidate proposed membership exactly matches the base policy membership.

Integrity failures fail closed before the mutation boundary.

## Explicit replacement metadata

The caller must supply:

- a new nonblank `policy_id` distinct from the base policy ID;
- an explicit nonblank `application_source_ref`;
- an explicit timezone-aware `attempted_at` timestamp.

The timestamp cannot predate the Step 2 preflight.

Step 3 introduces no internal wall clock and no random source.

## Exact operator-owned allocation values

The replacement policy is built with the existing `build_master_allocation_policy()` function.

Its envelopes are copied exactly from the immutable Step 1 change candidate, which itself copied the
operator-owned scenario selected in Batch 21f.

Step 3 does not:

- interpolate allocation scenarios;
- calculate capital ceilings;
- calculate open-risk ceilings;
- calculate gross-exposure ceilings;
- calculate Kelly sizing;
- infer statistical correlation;
- create optimization scores;
- invent allocation percentages or thresholds.

The replacement remains a normal static `MasterAllocationPolicy` with source
`OPERATOR_CONFIGURATION`.

## In-process atomic state

Step 3 adds `InMemoryMasterAllocationPolicyAtomicState` as the smallest executable state holder needed
to prove and exercise the compare-and-swap boundary.

It uses `threading.RLock` and stores one current `MasterAllocationPolicy`.

Its scope is explicit:

- `in_process_only = True`;
- `durable = False`;
- `multi_process_safe = False`;
- `live_ready = False`.

This state object is not presented as durable production configuration storage and is not a distributed
lock. A later LIVE-readiness step must provide an appropriate persistence/CAS adapter before this
boundary can be considered safe across multiple processes or hosts.

Step 3 does not hide that limitation behind an abstract claim of atomicity.

## Atomic compare-and-swap

The replacement operation compares, while holding the same `RLock` used for mutation:

- expected Master Portfolio ID;
- expected base policy ID;
- expected base policy SHA-256 fingerprint.

Only an exact match can replace the state.

The replacement also preserves exact crew membership.

Two concurrent attempts against the same base fingerprint cannot both succeed. The reference tests
prove that exactly one receives `APPLIED` and the other receives `CAS_CONFLICT`.

## Expected race behavior

A policy change between Step 2 preflight and Step 3 application is an expected operational race, not a
reason to silently overwrite newer state.

Step 3 returns an immutable receipt with:

- `status = CAS_CONFLICT`;
- `reason_code = ATOMIC_BASE_POLICY_MISMATCH`;
- `policy_mutation_performed = False`.

The policy observed under the mutation lock remains active.

Integrity failures remain exceptions; expected stale-state conflicts become auditable outcomes.

## Successful application behavior

An exact compare-and-swap returns:

- `status = APPLIED`;
- `reason_code = APPLIED`;
- `atomic_compare_and_swap_performed = True`;
- `base_policy_revalidated_at_mutation = True`;
- `policy_mutation_performed = True`.

The active state then contains the newly built `MasterAllocationPolicy`.

This is the first Batch 21g contract where policy mutation is intentionally true.

## Audit receipt

`MasterAllocationPolicyReplacementReceipt` binds:

- change-candidate ID and fingerprint;
- application-authorization ID and fingerprint;
- preflight ID and fingerprint;
- expected base policy ID and fingerprint;
- policy ID and fingerprint actually observed under the mutation lock;
- requested replacement policy ID and fingerprint;
- policy ID and fingerprint active after the attempt;
- explicit application source reference;
- operator reference inherited from the Step 2 authorization;
- explicit application timestamp;
- whether CAS occurred;
- whether the base policy was revalidated at mutation time;
- whether mutation actually happened.

The receipt is immutable and SHA-256 fingerprinted.

For `APPLIED`, the active post-attempt fingerprint must equal the requested new policy fingerprint.
For `CAS_CONFLICT`, the active post-attempt fingerprint must equal the policy observed under the lock.

## Replay safety

Reusing the same authorization/preflight after one successful replacement cannot overwrite the newly
active policy because the expected base fingerprint no longer matches.

A second attempt therefore returns `CAS_CONFLICT` instead of applying again.

This gives the one-shot authorization chain a natural stale-base protection without adding a hidden
mutable authorization-consumption registry.

## Static replacement is not dynamic allocation

A successful Step 3 replacement does not enable a dynamic allocator.

The new policy still exposes:

- `auto_apply = False`;
- `dynamic_allocation = False`;
- `reservation_authority = False`;
- `admission_authority = False`;
- `risk_authority = False`;
- `registry_mutation = False`;
- `live_authority = False`.

The Step 3 receipt likewise exposes `dynamic_allocation_enabled = False`.

Each future policy change still needs a complete accepted advisory/candidate/authorization/preflight/
CAS chain unless a later batch explicitly introduces another operator-approved mechanism.

## Risk and execution boundary

Neither the atomic state nor the replacement receipt can:

- approve a proposal rejected by local deterministic Risk;
- override the Master Risk Gate;
- reserve, commit, or release Master capital;
- resize a Risk-authorized proposal;
- mutate `AgentRegistry`;
- submit PAPER orders;
- mutate broker positions;
- arm LIVE;
- submit LIVE orders.

The local Risk Engine remains the trade-level risk authority and the Master Risk Gate remains veto-only.

## One physical Master capital

Changing allocation ceilings does not clone capital and Step 3 does not sum SHADOW/backtest equities.

The existing Batch 21 invariant remains unchanged: crew envelopes are ceilings over one physical Master
capital truth, not independent cash balances.

## No AI call

Step 3 performs no AI work.

It does not call:

- an AI provider;
- `AIGateway.generate_structured()`;
- `AIGatewayRequest`;
- the Master Professor.

The Master Professor reasoning remains sealed in Batch 21f.

## Contracts

Step 3 adds:

- `InMemoryMasterAllocationPolicyAtomicState`;
- `MasterAllocationPolicyReplacementStatus`;
- `MasterAllocationPolicyReplacementReasonCode`;
- `MasterAllocationPolicyReplacementReceipt`;
- `apply_master_allocation_policy_replacement()`;
- `master_allocation_policy_replacement_receipt_payload()`.

## Explicit Step 3 boundary

Step 3 does not:

- provide durable policy persistence;
- provide a distributed/multi-process CAS implementation;
- enable automatic or scheduled dynamic allocation;
- generate allocation numbers;
- change Portfolio membership;
- reserve Master capital;
- call local Risk;
- call the Master Risk Gate;
- mutate `AgentRegistry`;
- execute PAPER;
- arm or execute LIVE;
- call AI.

A later Batch 21g step can add durable state/adapters or evaluation/closure around policy replacement,
but it must preserve the exact operator authorization, stale-write, Risk, and LIVE boundaries already
established here.

## Validation in reconstruction harness

The reconstruction harness contains the real Batch 21f Steps 1–4 and Batch 21g Steps 1–2 contracts,
with lightweight stubs only for older project dependencies.

Validation performed for the new code:

- Batch 21g Step 3 targeted tests: 28 passed;
- cumulative Batch 21f Steps 1–4 + Batch 21g Steps 1–3 targeted tests: 190 passed;
- concurrent two-writer CAS test: exactly one `APPLIED`, one `CAS_CONFLICT`;
- Python compilation: passed;
- public `app.portfolio` import: passed;
- `app.evaluation` implicit import from `app.portfolio`: absent;
- Python source/test line length <= 100: passed.

The reconstruction harness is not the authoritative full repository checkout and does not contain Ruff.
Run Ruff, the targeted Step 3 tests, all Portfolio tests, and the complete repository suite in the real
checkout before commit.
