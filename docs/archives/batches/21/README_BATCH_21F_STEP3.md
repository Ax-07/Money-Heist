# Batch 21f — Step 3 — Master Professor SHADOW via AI Gateway

Baseline: `6bffcca` — Batch 21f Step 2 Master Professor Evidence Analysis Engine.

## Goal

Connect the deterministic Step 2 evidence analysis to the existing AI Gateway through a strict
Master Professor SHADOW adapter, while preserving the operator-owned allocation boundary established
in Step 1.

The path is:

`sealed 21e evidence -> Step 1 evidence -> Step 2 descriptive analysis -> AI Gateway -> strict
Master Professor SHADOW output -> Step 1 recommendation/report -> operator review -> STOP`.

Step 3 does not apply an allocation policy and cannot reach reservations, deterministic Risk, the
Master Risk Gate, PAPER execution, AgentRegistry mutation, or LIVE.

## Existing AI Gateway only

Step 3 does not create a provider client and does not call a provider directly.

`MasterProfessorStructuredGateway` is the minimal structural protocol implemented by the existing
`AIGateway.generate_structured()` API. The runtime builds a normal `AIGatewayRequest` and requests a
strict Pydantic `MasterProfessorShadowOutput`.

Provider routing, budget reservation, retries, structured-output parsing and AI usage accounting
therefore remain owned by the existing AI Gateway.

The Master Professor adapter imports only the AI Gateway request/result contracts. It does not create
another gateway or routing engine.

## No registry mutation

Step 3 identifies the SHADOW role with the fixed adapter identity:

`master-professor`.

It does not add, remove, promote or mutate an `AgentRegistry` entry. Model route and prompt version are
explicit operator-owned gateway configuration inputs for this advisory adapter.

A later architecture step may register a permanent agent identity if required, but this runtime does
not need registry mutation to perform an analysis-only gateway call.

## Operator-owned AI configuration

`MasterProfessorShadowGatewayConfig` binds:

- prompt version;
- model route;
- maximum output tokens;
- operator/source reference.

The configuration is immutable and SHA-256 fingerprinted.

It explicitly states:

- `gateway_required = True`;
- `provider_direct_access = False`;
- `mode = SHADOW`;
- `live_authority = False`.

Step 3 does not invent a model route, prompt version or output budget.

## Critical allocation-number boundary

The Master Professor is **not allowed to invent allocation numbers** in Step 3.

Instead, an operator may supply zero or more complete `MasterProfessorAllocationCandidate` scenarios.
Each scenario contains a full configured `CrewAllocationEnvelope` for every current crew.

Every candidate:

- is explicitly tagged `OPERATOR_SCENARIO`;
- carries an operator/source reference;
- is immutable and fingerprinted;
- contains only configured envelopes;
- preserves exact current crew membership;
- must actually differ from the current policy before it can be exposed to the model;
- grants no policy, Risk or LIVE authority.

The strict AI output contains only `selected_candidate_id`; it contains **no allocation amount fields**.

For `PROPOSE_CHANGE`, the selected ID must match one of the supplied operator scenarios exactly. The
runtime maps that ID back to the immutable operator-owned envelopes after the AI response has been
validated.

The model therefore cannot interpolate, resize, optimize or fabricate capital, open-risk or gross
exposure ceilings.

## Three possible advisory actions

The structured output reuses the Step 1 action contract:

- `KEEP_CURRENT`;
- `PROPOSE_CHANGE`;
- `ABSTAIN`.

`KEEP_CURRENT` cannot select a candidate and is deterministically mapped to the current allocation
policy envelopes.

`PROPOSE_CHANGE` must select exactly one existing operator candidate.

`ABSTAIN` cannot select a candidate and produces no proposed envelopes.

The resulting object is then passed through the existing Step 1
`build_master_allocation_advisory_recommendation()` and
`build_master_allocation_advisory_report()` functions. Step 3 does not create a parallel recommendation
contract.

## Current policy must already be configured

Step 3 refuses to invoke the Master Professor when the current allocation policy is
`NOT_CONFIGURED`.

The existing Step 1 fail-closed behavior remains the correct path in that case: advisory `ABSTAIN`.

This prevents the model from filling missing production ceilings with invented values merely because
an AI call is available.

## Exact Step 2 provenance

Before any gateway call, Step 3 revalidates:

- current `MasterAllocationPolicy` fingerprint;
- Step 2 analysis fingerprint;
- Master Portfolio identity;
- Step 2 binding to the exact current policy fingerprint;
- every Step 1 advisory evidence item through the Step 1 evidence constructor;
- exact ordered evidence fingerprints represented by the Step 2 analysis;
- every operator candidate fingerprint and crew membership.

Invalid or stale context fails before the gateway is called.

This makes the dependency explicit:

`verified Step 1 evidence -> exact Step 2 analysis -> one SHADOW gateway request`.

## Deterministic gateway request identity

`build_master_professor_shadow_gateway_request()` derives its request UUID from:

- Master Portfolio ID;
- Step 2 analysis fingerprint;
- current allocation policy fingerprint;
- canonical operator candidate fingerprints;
- gateway configuration fingerprint.

Candidate input order therefore cannot change the request identity or canonical input payload.

A new analysis, policy, candidate scenario or gateway configuration produces a different request
identity.

The runtime still records the real gateway route/model/provider request evidence returned by the
existing gateway.

## Grounded model context

The AI input contains only:

- current operator-owned allocation policy and envelopes;
- Step 2 analysis identity and evidence fingerprints;
- Step 2 descriptive reason codes;
- exact regime provenance;
- per-crew descriptive analyses;
- pairwise descriptive comparisons;
- operator candidate scenarios;
- an explicit allowlist of evidence fingerprints that may be cited.

It does not provide a hidden optimization objective or a production sizing formula.

The prompt explicitly forbids:

- invented allocation amounts;
- interpolation between candidates;
- composite scores;
- final rankings;
- Kelly sizing;
- inferred statistical correlation;
- invented thresholds;
- orders or reservations;
- local Risk or Master admission decisions;
- registry mutation;
- broker actions;
- LIVE actions.

## Strict structured output

`MasterProfessorShadowOutput` uses `extra="forbid"` and immutable Pydantic fields.

It must echo the exact:

- Step 2 analysis ID;
- Step 2 analysis fingerprint;
- current allocation policy fingerprint.

It contains:

- advisory action;
- optional selected operator candidate ID;
- rationale codes;
- evidence fingerprint references;
- summary;
- explicit uncertainties.

Every cited evidence reference must belong to the allowlist supplied with the request. A fabricated or
unrelated fingerprint is rejected after the gateway call.

The schema structurally fixes the following authority fields:

- `advisory_only = True`;
- `operator_review_required = True`;
- `auto_apply = False`;
- `numeric_allocation_generation = False`;
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

A provider response attempting to set one of those forbidden authorities to true fails structured
output validation.

## AI usage evidence

Step 3 preserves the AI Gateway usage returned for the request, including retry-response usage when
present.

Each local `MasterProfessorShadowUsageRecord` binds:

- usage ID;
- request ID;
- Master Portfolio/system ID;
- agent ID;
- route ID;
- model ID;
- input/cached/output tokens;
- estimated EUR cost;
- latency;
- attempt number;
- usage timestamp.

The runtime requires usage records to belong to the same request, Master Portfolio, Master Professor,
route and model as the returned gateway result.

`total_ai_cost_eur` is the exact sum of the gateway usage records represented by the Step 3 result. It
is not inferred from historical trading results.

## Final SHADOW result

`MasterProfessorShadowAdvisoryResult` binds:

- Step 2 analysis provenance;
- current allocation policy fingerprint;
- canonical candidate fingerprints;
- gateway configuration fingerprint;
- gateway request/route/model/provider evidence;
- exact AI usage evidence and cost;
- strict model output;
- Step 1 recommendation fingerprint;
- complete Step 1 advisory report.

The result is immutable and fingerprinted.

It exposes the same hard authority boundary as the model output: advisory only, mandatory operator
review, no automatic policy change, no Risk authority, no broker authority and no LIVE authority.

## Failure behavior

Step 3 fails closed before or after the AI call when, for example:

- the current policy is not configured;
- the current policy fingerprint is stale;
- the Step 2 analysis fingerprint is stale;
- analysis and evidence do not share exact provenance;
- a candidate changes crew membership;
- a candidate reproduces the current policy while claiming to be a change option;
- the output references another analysis or policy;
- `PROPOSE_CHANGE` selects an unknown candidate;
- the output cites evidence outside the supplied allowlist;
- gateway request identity is mismatched;
- AI usage evidence belongs to another request/route/model/agent/system.

No fallback silently invents an allocation.

## Contracts

Step 3 adds:

- `MASTER_PROFESSOR_AGENT_ID`;
- `MasterProfessorAllocationCandidateSource`;
- `MasterProfessorAllocationCandidate`;
- `MasterProfessorShadowGatewayConfig`;
- `MasterProfessorShadowOutput`;
- `MasterProfessorStructuredGateway`;
- `MasterProfessorShadowUsageRecord`;
- `MasterProfessorShadowStatus`;
- `MasterProfessorShadowAdvisoryResult`;
- `build_master_professor_allocation_candidate()`;
- `build_master_professor_shadow_gateway_config()`;
- `build_master_professor_shadow_gateway_request()`;
- `validate_master_professor_shadow_output()`;
- `run_master_professor_shadow_advisory()`.

## Explicit Step 3 boundary

Step 3 does not:

- generate numeric allocation ceilings;
- optimize allocation percentages;
- calculate Kelly sizing;
- infer statistical correlation;
- create a composite score;
- create an automatic ranking;
- mutate `MasterAllocationPolicy`;
- apply an advisory recommendation;
- reserve or commit capital;
- override deterministic local Risk;
- override the Master Risk Gate;
- resize a Risk-authorized trade;
- mutate `AgentRegistry`;
- submit PAPER orders;
- arm LIVE;
- create a real order.

A later Batch 21f step may add operator decision/acceptance recording or SHADOW recommendation
evaluation without weakening these boundaries.

## Validation in generation harness

The reconstruction harness uses the real Batch 21 Step 1/2/3 Portfolio contracts and lightweight
compatibility stubs only for pre-Batch-21 dependencies that are present in the real checkout.

Validation performed on the generated Step 3 source:

- Step 3 targeted tests: 27 passed;
- Step 1 + Step 2 + Step 3 targeted tests: 83 passed;
- Python compilation: passed;
- public `app.portfolio` import: passed in the reconstruction harness;
- `app.evaluation` implicit import from `app.portfolio`: absent;
- Python source/test line length <= 100: passed.

The reconstruction harness is not the complete repository checkout and does not contain Ruff. Run
Ruff, the Step 3 tests, all Portfolio tests and the complete repository suite in the real checkout
before commit.
