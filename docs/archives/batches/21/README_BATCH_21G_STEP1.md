# Batch 21g — Step 1 — Allocation Policy Change Boundary

Baseline: `885d0c8` — Batch 21f closed by the Master Professor operator-review audit seal.

## Goal

Introduce the first boundary between a human-accepted SHADOW allocation advisory and any future
production allocation-policy change, without applying a policy mutation.

The Step 1 path is intentionally limited to:

`accepted + VERIFIED + SEALED Batch 21f PROPOSE_CHANGE -> immutable policy-change candidate -> STOP`.

The new candidate is evidence for a later explicit policy-application authorization step. It is not a
replacement `MasterAllocationPolicy` and it grants no reservation, Risk, broker, or LIVE authority.

## Why this step exists

Batch 21f deliberately ended at a sealed human-reviewed advisory record. Even an operator `ACCEPT`
meant only that the SHADOW recommendation itself had been accepted for the audit record.

Batch 21g Step 1 preserves that boundary. It does not reinterpret the prior acceptance as permission
to mutate production configuration.

Instead it creates a distinct immutable `MasterAllocationPolicyChangeCandidate` that can only be
built from an accepted and sealed `PROPOSE_CHANGE` chain.

## Eligibility

A policy-change candidate can be created only when all of the following are true:

- the current `MasterAllocationPolicy` is still `CONFIGURED`;
- its fingerprint is intact;
- the Step 3 Master Professor SHADOW result is `COMPLETED` and intact;
- the Step 1 advisory recommendation is exactly `PROPOSE_CHANGE`;
- the Step 4 operator action is exactly `ACCEPT`;
- the Step 4 operator status is exactly `ACCEPTED`;
- the Step 4 advisory audit is `VERIFIED`;
- the Step 4 advisory closure is `SEALED`;
- the selected operator scenario identity is preserved through Step 3 and Step 4;
- the selected operator scenario fingerprint is one of the candidate fingerprints represented by
  the Step 3 result;
- its proposed envelopes exactly equal the already reviewed Step 1 recommendation envelopes;
- its crew membership exactly matches the current policy;
- its envelopes are fully `CONFIGURED`;
- the proposed envelopes actually differ from the current policy.

`KEEP_CURRENT`, `ABSTAIN`, `REJECT`, and `DEFER` therefore cannot produce a policy-change candidate.

## Exact operator-owned values

Step 1 does not generate allocation values.

The proposed envelopes are copied exactly from the `MasterProfessorAllocationCandidate` selected in
Batch 21f Step 3. That candidate was already required to be an explicit `OPERATOR_SCENARIO` containing
complete configured envelopes.

Step 1 cannot:

- interpolate between scenarios;
- calculate new capital ceilings;
- calculate new open-risk ceilings;
- calculate new gross-exposure ceilings;
- optimize allocation percentages;
- use Kelly sizing;
- infer statistical correlation;
- invent a production threshold.

## Base-policy stale-write protection

The policy-change candidate records both:

- `base_policy_id`;
- `base_policy_fingerprint_sha256`.

This is a critical precondition for later application work. A future policy-application mechanism can
require that the then-current policy fingerprint is still exactly this base fingerprint before it is
allowed to proceed.

Step 1 itself does not perform that future application. It only makes the stale-write guard auditable.

## Complete provenance binding

The candidate binds the exact fingerprints for:

- the current/base allocation policy;
- the selected operator scenario;
- the Step 3 Master Professor SHADOW result;
- the Step 1 advisory recommendation;
- the Step 4 operator decision;
- the Step 4 advisory audit;
- the Step 4 advisory closure.

It also preserves:

- the selected operator candidate ID;
- the selected operator candidate source reference;
- the human operator reference from Step 4;
- the exact reviewed/sealed timestamp.

The builder re-hashes the critical source objects rather than trusting stored fingerprints alone.

It also rebuilds the Step 4 closure from the supplied audit and operator decision and requires exact
equality with the supplied closure.

## Candidate is not a production policy

`MasterAllocationPolicyChangeCandidate` is intentionally a separate contract.

It does not create or return a new `MasterAllocationPolicy`.

It therefore has no new production `policy_id`, no active-policy replacement semantics, and no method
to install itself into Portfolio state.

Its proposed envelopes remain candidate data only.

## Explicit future authorization boundary

Every valid candidate exposes:

- `candidate_only = True`;
- `explicit_policy_application_authorization_required = True`;
- `policy_application_performed = False`;
- `policy_application_authority = False`;
- `auto_apply = False`;
- `dynamic_allocation_enabled = False`.

This means the existing human `ACCEPT` from Batch 21f cannot be silently reused as an application
authorization.

A later Batch 21g step must introduce a separate explicit policy-application authorization and
preflight check before any mutation can exist.

## Risk and execution boundary

The candidate structurally exposes false authority flags for:

- reservation mutation;
- deterministic Risk;
- Master admission;
- local Risk override;
- resizing;
- AgentRegistry mutation;
- broker execution;
- LIVE execution;
- automatic execution.

The local Risk Engine remains the trade-level risk authority. The Master Risk Gate remains veto-only.

## No AI call

Step 1 performs no AI work.

It does not call:

- an AI provider;
- `AIGateway.generate_structured()`;
- `AIGatewayRequest`;
- the Master Professor again.

All Master Professor reasoning already happened in Batch 21f Step 3.

## One physical Master capital

Step 1 does not aggregate capital, equity, historical replay balances, or SHADOW branch values.

Crew envelope values remain ceilings inside one physical Master-capital model. They are not cloned
cash balances.

## Determinism

The policy-change candidate ID and fingerprint are derived from canonical existing evidence only.

No wall-clock timestamp or random source is introduced.

`reviewed_at` is inherited exactly from the sealed Batch 21f operator-review closure.

Rebuilding from the same valid source chain yields the same candidate ID and SHA-256 fingerprint.

## Contracts

Step 1 adds:

- `MasterAllocationPolicyChangeCandidateStatus`;
- `MasterAllocationPolicyChangeCandidateSource`;
- `MasterAllocationPolicyChangeCandidate`;
- `build_master_allocation_policy_change_candidate()`;
- `master_allocation_policy_change_candidate_payload()`.

## Explicit Step 1 boundary

Step 1 does not:

- authorize policy application;
- mutate `MasterAllocationPolicy`;
- build a replacement active production policy;
- change Portfolio membership;
- reserve, commit, or release capital;
- call local Risk;
- call the Master Risk Gate;
- resize a Risk-authorized trade;
- mutate `AgentRegistry`;
- submit PAPER orders;
- arm LIVE;
- submit LIVE orders;
- call AI;
- enable dynamic allocation.

A later Batch 21g step can add an explicit operator-owned application authorization and deterministic
preflight barrier. That later step must still validate the base-policy fingerprint before any policy
mutation is considered.

## Validation in reconstruction harness

The reconstruction harness contains the real Batch 21f Step 1–4 contracts and lightweight stubs for
older dependencies.

Validation performed for the new code:

- Batch 21g Step 1 targeted tests: 25 passed;
- cumulative Batch 21f Step 1–4 + Batch 21g Step 1 targeted tests: 134 passed;
- Python compilation: passed;
- public `app.portfolio` import: passed;
- `app.evaluation` implicit import from `app.portfolio`: absent;
- Python source/test line length <= 100: passed;
- no AI Gateway/provider invocation in the new module.

The reconstructed harness cannot serve as the full `tests/portfolio` authority because its pre-Batch-21
compatibility stubs already fail 245 unrelated tests on the unchanged baseline. The unchanged baseline
produces 245 failed / 425 passed there, while the Step 1 overlay produces the same 245 pre-existing
failures plus the 25 new passing tests.

Run Ruff, the targeted Step 1 tests, all Portfolio tests, and the complete repository suite in the real
checkout before commit.
