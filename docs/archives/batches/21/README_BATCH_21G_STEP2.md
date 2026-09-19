# Batch 21g — Step 2 — Explicit Policy Application Authorization + Deterministic Preflight

Baseline: `ce4c0aa` — Batch 21g Step 1 Allocation Policy Change Boundary.

## Goal

Add the second explicit human boundary required before any allocation-policy mutation can even be
considered, then evaluate a deterministic read-only preflight against the current Master allocation
policy.

The Step 2 path is intentionally limited to:

`21g Step 1 policy-change candidate -> explicit operator AUTHORIZE / REJECT / DEFER -> deterministic
preflight -> READY_FOR_APPLICATION / BLOCKED -> STOP`.

Step 2 does not build, install, replace, persist, or activate a `MasterAllocationPolicy`.

## Why a second operator decision exists

Batch 21f operator `ACCEPT` means only that the SHADOW advisory was accepted as a reviewed advisory
record.

Batch 21g Step 1 converts that accepted and sealed advisory into an immutable policy-change candidate,
but still exposes:

- `explicit_policy_application_authorization_required = True`;
- `policy_application_performed = False`;
- `policy_application_authority = False`.

Step 2 therefore introduces a new operator decision whose scope is exactly one Step 1 change
candidate. The prior 21f acceptance cannot be reused silently as application authorization.

## Explicit application authorization

`MasterAllocationPolicyApplicationAuthorizationAction` defines:

- `AUTHORIZE`;
- `REJECT`;
- `DEFER`.

They map deterministically to:

- `AUTHORIZED`;
- `REJECTED`;
- `DEFERRED`.

`MasterAllocationPolicyApplicationAuthorization` binds:

- the exact Master Portfolio ID;
- the exact Step 1 change-candidate ID;
- the exact Step 1 change-candidate fingerprint;
- the exact base-policy ID;
- the exact base-policy fingerprint;
- an explicit operator reference;
- canonical rationale codes;
- an explicit timezone-aware operator decision timestamp.

The authorization builder re-hashes the Step 1 candidate before recording the decision.

The decision timestamp must not predate the human advisory review timestamp carried by the candidate.
No wall-clock time is generated internally.

## Authorization is not mutation

Even an `AUTHORIZED` record does not directly mutate policy state.

The authorization structurally exposes:

- `human_operator_required = True`;
- `single_candidate_scope = True`;
- `deterministic_preflight_required = True`;
- `atomic_compare_and_swap_required = True`;
- `policy_application_performed = False`;
- `runtime_policy_application_authority = False`;
- `auto_apply = False`;
- `dynamic_allocation_enabled = False`.

It also grants no reservation, Risk, admission, resize, registry, broker, PAPER, or LIVE authority.

The meaning of `AUTHORIZE` is therefore only:

> this exact candidate may proceed to the deterministic preflight boundary.

It is not an executable command.

## Deterministic preflight

`evaluate_master_allocation_policy_application_preflight()` accepts:

- one intact Step 1 change candidate;
- one intact Step 2 operator authorization bound to that candidate;
- the current `MasterAllocationPolicy` observed by the caller;
- an explicit timezone-aware preflight timestamp.

It never mutates those inputs.

The preflight returns exactly one of:

- `READY_FOR_APPLICATION`;
- `BLOCKED`.

## READY_FOR_APPLICATION conditions

The result is `READY_FOR_APPLICATION` only when all of the following remain true at preflight time:

- the new operator action is `AUTHORIZE` / `AUTHORIZED`;
- the current Master Portfolio ID equals the candidate Master Portfolio ID;
- the current policy ID equals the candidate base-policy ID;
- the current policy fingerprint equals the candidate base-policy fingerprint;
- the current policy is still `CONFIGURED`;
- current policy membership exactly matches the candidate proposed-envelope membership;
- the candidate and authorization fingerprints are intact;
- the authorization is bound to the exact candidate and base policy.

A ready result carries only the reason code `READY`.

## BLOCKED reason codes

A valid non-ready preflight is represented as an immutable `BLOCKED` result instead of silently
continuing.

Possible deterministic reason codes are:

- `OPERATOR_REJECTED`;
- `OPERATOR_DEFERRED`;
- `MASTER_PORTFOLIO_MISMATCH`;
- `BASE_POLICY_ID_MISMATCH`;
- `BASE_POLICY_FINGERPRINT_MISMATCH`;
- `BASE_POLICY_NOT_CONFIGURED`;
- `MEMBERSHIP_MISMATCH`.

Multiple independent reasons may be present. They are canonicalized, sorted, unique, and
fingerprinted.

Expected operational staleness is therefore auditable rather than converted into an exception.
Integrity failures still fail closed with an exception.

## Base-policy stale-write guard

Batch 21g Step 1 recorded:

- `base_policy_id`;
- `base_policy_fingerprint_sha256`.

Step 2 compares the currently supplied policy against both values.

If a different policy has been installed, if the same policy ID now has different content, if
membership changed, or if configuration disappeared, the preflight is `BLOCKED`.

This is the first concrete stale-write guard for future allocation-policy application.

## TOCTOU protection remains mandatory

A `READY_FOR_APPLICATION` preflight is evidence about the policy state observed at `checked_at`.

It is not a lock and does not consume or reserve the base policy.

For that reason every preflight structurally exposes:

- `preflight_only = True`;
- `atomic_compare_and_swap_still_required = True`;
- `policy_application_performed = False`.

A later application step must re-check the exact base-policy fingerprint atomically at mutation time.
It must not assume that a previously ready preflight is still current.

This avoids a time-of-check/time-of-use gap between Step 2 and future policy installation.

## Verification flags

The preflight records explicit deterministic booleans:

- `operator_authorization_verified`;
- `base_policy_identity_verified`;
- `base_policy_fingerprint_verified`;
- `membership_verified`;
- `configuration_verified`.

The dataclass validates that these flags are consistent with the reason codes. A caller cannot build a
fingerprinted `READY_FOR_APPLICATION` record while setting one of the required verification flags to
false.

## No new allocation numbers

Step 2 does not generate or alter allocation values.

The proposed envelopes remain the exact operator-owned values already carried by the Step 1 candidate.
Step 2 does not:

- interpolate between scenarios;
- calculate capital ceilings;
- calculate open-risk ceilings;
- calculate gross-exposure ceilings;
- optimize allocation percentages;
- calculate Kelly sizing;
- infer statistical correlations;
- invent thresholds or scores.

## No MasterAllocationPolicy construction

Neither the authorization nor the preflight contains a new production `policy_id`.

Step 2 does not call `build_master_allocation_policy()` and exposes no `apply()` method.

A future step may introduce a narrowly scoped policy replacement operation, but only after exact
revalidation of the candidate, authorization, preflight, and current base-policy fingerprint.

## Risk and trading boundary

Neither Step 2 object can:

- reserve, commit, or release capital;
- approve a trade rejected by local deterministic Risk;
- override the Master Risk Gate;
- resize a Risk-authorized proposal;
- mutate `AgentRegistry`;
- submit PAPER orders;
- mutate broker state;
- arm LIVE;
- submit LIVE orders.

The local Risk Engine remains the trade-level risk authority and the Master Risk Gate remains veto-only.

## No AI call

Step 2 performs no AI work.

It does not call:

- an AI provider;
- `AIGateway.generate_structured()`;
- `AIGatewayRequest`;
- the Master Professor.

The complete Master Professor reasoning path remains sealed in Batch 21f.

## One physical Master capital

Step 2 does not aggregate capital or equity.

Crew allocation envelopes remain ceilings within one physical Master-capital model and are not cloned
cash balances.

## Determinism

Authorization and preflight IDs/fingerprints use the existing stable canonical digest mechanism.

No random source or internal wall clock is introduced.

The same candidate, operator decision inputs, current policy, and explicit timestamps produce the same
artifacts.

## Contracts

Step 2 adds:

- `MasterAllocationPolicyApplicationAuthorizationAction`;
- `MasterAllocationPolicyApplicationAuthorizationStatus`;
- `MasterAllocationPolicyApplicationAuthorization`;
- `MasterAllocationPolicyApplicationPreflightStatus`;
- `MasterAllocationPolicyApplicationPreflightReasonCode`;
- `MasterAllocationPolicyApplicationPreflight`;
- `build_master_allocation_policy_application_authorization()`;
- `evaluate_master_allocation_policy_application_preflight()`;
- deterministic payload helpers for authorization and preflight fingerprints.

## Explicit Step 2 boundary

Step 2 does not:

- mutate `MasterAllocationPolicy`;
- build the replacement active policy;
- persist a policy;
- provide an atomic compare-and-swap implementation;
- reserve Master capital;
- call local Risk;
- call the Master Risk Gate;
- execute PAPER;
- arm or execute LIVE;
- call AI;
- enable dynamic allocation.

The likely next step is an atomic, operator-owned policy replacement primitive that accepts only an
exact `READY_FOR_APPLICATION` preflight and re-checks the base-policy fingerprint at the mutation
boundary.

## Validation in reconstruction harness

The reconstruction harness contains the real Batch 21f Step 1–4 and Batch 21g Step 1 contracts, with
lightweight stubs only for older project dependencies.

Validation performed for the new code:

- Batch 21g Step 2 targeted tests: 28 passed;
- cumulative Batch 21f Step 1–4 + Batch 21g Step 1–2 targeted tests: 162 passed;
- Python compilation: passed;
- public `app.portfolio` import: passed;
- `app.evaluation` implicit import from `app.portfolio`: absent;
- Python source/test line length <= 100: passed;
- no AI Gateway/provider invocation in the new module.

The reconstruction harness is not the authoritative full repository checkout. Run Ruff, the targeted
Step 2 tests, all Portfolio tests, and the complete repository suite in the real checkout before commit.
