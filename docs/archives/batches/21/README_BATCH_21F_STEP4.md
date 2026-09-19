# Batch 21f — Step 4 — Operator Review & Advisory Audit Closure

Baseline: `5670755` — Batch 21f Step 3 Master Professor SHADOW via AI Gateway.

## Goal

Close the Batch 21f SHADOW allocation-advisory chain with an explicit human operator review,
a deterministic audit report, and an immutable closure seal.

The Step 4 path is intentionally limited to:

`Step 1 sealed advisory evidence -> Step 2 deterministic analysis -> Step 3 Master Professor SHADOW
result -> operator ACCEPT / REJECT / DEFER -> audit VERIFIED -> closure SEALED -> STOP`.

Step 4 records and seals a human review. It does **not** apply a new allocation policy.

## Operator review actions

`MasterProfessorOperatorReviewAction` defines exactly three review actions:

- `ACCEPT`;
- `REJECT`;
- `DEFER`.

They map deterministically to:

- `ACCEPTED`;
- `REJECTED`;
- `DEFERRED`.

The action is an operator decision about the SHADOW advisory record only.

`ACCEPT` does not mean that the runtime is authorized to mutate the current allocation policy.

## ACCEPT is not APPLY

This distinction is structural rather than prompt-only.

`MasterProfessorOperatorReviewDecision` exposes:

- `human_operator_required = True`;
- `operator_decision_recorded = True`;
- `advisory_acceptance_only = True`;
- `allocation_application_performed = False`;
- `allocation_application_authority = False`;
- `policy_mutation = False`;
- `reservation_authority = False`;
- `risk_authority = False`;
- `admission_authority = False`;
- `local_risk_override = False`;
- `resize_authority = False`;
- `registry_mutation = False`;
- `broker_authority = False`;
- `live_authority = False`;
- `auto_execute = False`.

An accepted `PROPOSE_CHANGE` recommendation therefore remains a reviewed SHADOW recommendation.

Any later policy-change mechanism must be a separate explicit operator-owned step with its own
safety and provenance boundary.

## Exact source binding

Before a review decision can be built, Step 4 validates the exact Step 1 -> Step 3 chain.

It re-hashes the supplied Step 2 analysis and Step 3 SHADOW result instead of trusting their stored
fingerprints.

It also validates:

- Step 3 result status is `COMPLETED`;
- Step 3 analysis ID equals the supplied Step 2 analysis ID;
- Step 3 analysis fingerprint equals the supplied Step 2 fingerprint;
- Master Portfolio identity is unchanged;
- the Step 1 advisory report fingerprint is intact;
- the Step 1 recommendation fingerprint is intact;
- the current `MasterAllocationPolicy` fingerprint is intact;
- the Step 2 and Step 3 current-policy fingerprints both bind that exact policy;
- every Step 1 advisory evidence item can be rebuilt through the Step 1 constructor;
- Step 1 evidence fingerprints exactly match the Step 2 evidence fingerprint sequence;
- every Step 3 AI usage record has an intact fingerprint;
- every Step 3 AI usage record belongs to the fixed Master Professor identity.

Post-construction tampering therefore fails closed.

## Human review provenance

`MasterProfessorOperatorReviewDecision` records:

- deterministic decision ID;
- exact Master Portfolio ID;
- Step 2 analysis fingerprint;
- Step 3 SHADOW-result fingerprint;
- Step 1 advisory-report fingerprint;
- Step 1 recommendation fingerprint;
- current allocation-policy fingerprint;
- original recommendation action;
- selected operator candidate ID when the recommendation is `PROPOSE_CHANGE`;
- explicit `operator_ref`;
- canonical rationale codes;
- explicit timezone-aware `decided_at`.

The operator reference is an audit reference supplied by the surrounding operator workflow.

Step 4 does not implement authentication, authorization, identity management, or a UI login system.
Those remain operational concerns outside this Portfolio contract.

## Review time

`decided_at` is explicit input and must not predate the latest AI usage timestamp represented by the
Step 3 result.

Step 4 introduces no wall-clock timestamp of its own.

The same source result and the same operator review input produce the same decision ID and
fingerprint.

## Selected candidate identity

For a Step 3 `PROPOSE_CHANGE`, the operator review preserves the exact `selected_candidate_id`
returned by the already validated Step 3 result.

The Step 4 runtime does not:

- alter that candidate ID;
- create another candidate;
- interpolate between candidates;
- generate allocation amounts;
- rebuild a replacement allocation policy.

The exact proposed envelope values remain bound through the Step 1 recommendation fingerprint and
the Step 3 SHADOW-result fingerprint.

For `KEEP_CURRENT` or `ABSTAIN`, no selected candidate ID is permitted.

## Audit report

`audit_master_professor_advisory_review()` produces an immutable
`MasterProfessorAdvisoryAuditReport` with status `VERIFIED`.

The audit binds:

- Step 2 analysis identity and fingerprint;
- Step 3 SHADOW-result fingerprint;
- Step 1 advisory-report fingerprint;
- Step 1 recommendation fingerprint;
- current-policy fingerprint;
- operator-decision fingerprint;
- operator action and status;
- recommendation action;
- selected candidate identity when present;
- exact operator review timestamp.

The audit exposes explicit verification flags:

- `step1_evidence_chain_verified = True`;
- `step2_analysis_verified = True`;
- `step3_shadow_gateway_verified = True`;
- `operator_review_verified = True`;
- `no_policy_application_verified = True`;
- `no_trading_authority_verified = True`.

Every verification flag is required to be true for a valid audit object.

## Closure seal

`seal_master_professor_advisory_review()` accepts only a valid `VERIFIED` audit and the exact
operator decision referenced by that audit.

It produces `MasterProfessorAdvisoryClosureSeal` with status `SEALED`.

The seal binds:

- analysis fingerprint;
- SHADOW-result fingerprint;
- advisory-report fingerprint;
- recommendation fingerprint;
- current-policy fingerprint;
- operator-decision fingerprint;
- audit fingerprint;
- review action/status;
- recommendation action;
- selected candidate ID when present;
- deterministic `sealed_at` equal to the operator decision timestamp.

The seal does not contain a replacement allocation policy and does not provide a policy-application
method.

## REJECT and DEFER are auditable outcomes

`REJECT` and `DEFER` can be audited and sealed exactly like `ACCEPT`.

This is intentional: the historical record must preserve what the operator actually decided rather
than treating only accepted recommendations as meaningful evidence.

A deferred review remains non-executing and does not silently become accepted later.

Any later review is a separate explicit operator event.

## No additional AI call

Step 4 does not call:

- an AI provider;
- `AIGateway.generate_structured()`;
- a core agent;
- the Master Professor runtime again.

The AI work is already complete in Step 3.

Step 4 only validates, records, audits, and seals the result of that work.

## No production numeric invention

Step 4 introduces no new capital, open-risk, gross-exposure, correlation, sizing, scoring, or
optimization value.

In particular it does not:

- generate capital ceilings;
- generate risk ceilings;
- generate gross-exposure ceilings;
- calculate Kelly fractions;
- infer statistical correlations;
- add ranking thresholds;
- create dynamic allocation percentages.

## Risk and execution boundary

Neither the operator decision, audit, nor closure can:

- override local deterministic Risk;
- override the Master Portfolio Risk Gate;
- resize a Risk-authorized proposal;
- reserve capital;
- commit capital;
- release reservations;
- submit PAPER orders;
- mutate broker state;
- mutate `AgentRegistry`;
- arm LIVE;
- submit LIVE orders.

The Risk Engine remains the local risk authority and the existing Master Risk Gate remains
veto-only.

## One physical Master capital

Step 4 does not aggregate capital or equity.

It only binds fingerprints from the existing advisory chain.

The Batch 21 invariant remains unchanged: SHADOW/backtest equities are counterfactual and must never
be summed into physical Master capital.

## Determinism

Decision, audit, and closure IDs/fingerprints use the existing stable canonical digest mechanism.

No random source is introduced.

No wall-clock timestamp is generated.

The closure seal uses the exact explicit operator-review timestamp as `sealed_at`.

## Contracts

Step 4 adds:

- `MasterProfessorOperatorReviewAction`;
- `MasterProfessorOperatorReviewStatus`;
- `MasterProfessorOperatorReviewDecision`;
- `MasterProfessorAdvisoryAuditStatus`;
- `MasterProfessorAdvisoryAuditReport`;
- `MasterProfessorAdvisoryClosureStatus`;
- `MasterProfessorAdvisoryClosureSeal`;
- `build_master_professor_operator_review_decision()`;
- `audit_master_professor_advisory_review()`;
- `seal_master_professor_advisory_review()`.

## Batch 21f closure boundary

With Step 4, Batch 21f has a complete SHADOW advisory lifecycle:

1. Step 1 — sealed evidence and advisory recommendation/report contracts;
2. Step 2 — deterministic descriptive evidence analysis;
3. Step 3 — Master Professor SHADOW reasoning through the existing AI Gateway;
4. Step 4 — explicit operator review, audit, and closure seal.

The lifecycle ends at a sealed human-reviewed advisory record.

It does **not** end at a dynamically applied allocation.

Dynamic allocation remains a separate Batch 21g concern and must not be enabled merely because an
operator accepted a SHADOW recommendation.

## Explicit Step 4 boundary

Step 4 does not:

- authenticate an operator;
- provide a review UI;
- mutate `MasterAllocationPolicy`;
- build a replacement production policy;
- automatically apply accepted envelopes;
- touch reservations;
- call Risk;
- call the Master Risk Gate;
- call a broker;
- mutate `AgentRegistry`;
- execute PAPER;
- arm or execute LIVE;
- call AI again.

## Validation in generation harness

The reconstruction harness validates the new Step 4 contracts against the existing Step 1, Step 2,
and Step 3 targeted tests.

Validation performed:

- Step 4 targeted tests: 26 passed;
- cumulative Batch 21f Step 1 -> Step 4 targeted tests: 109 passed;
- Python compilation: passed;
- public `app.portfolio` import: passed;
- `app.evaluation` implicit import from `app.portfolio`: absent;
- Python source/test line length <= 100: passed.

The reconstruction harness is not the complete repository checkout and does not contain Ruff.
Run Ruff, the Step 4 targeted tests, all Portfolio tests, and the complete repository suite in the
real checkout before commit.
