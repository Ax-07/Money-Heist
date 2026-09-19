# Batch 21f — Step 1 — Master Allocation Advisory Contracts

Baseline: `14b22d6` — Batch 21e closed by the Master Historical Replay Closure & Audit Seal.

## Goal

Establish the read-only contracts for the future Master Professor / allocation-advisory layer
without creating dynamic allocation authority.

The Step 1 path is intentionally limited to:

`sealed Batch 21e replay evidence -> SHADOW recommendation contract -> operator-review report`.

No allocation policy is mutated and no recommendation can reach reservation, Risk, broker or LIVE.

## Architectural role

The project master architecture assigns the future Master Professor / Allocator the
responsibility to:

- compare systems;
- analyze performance according to regimes;
- recommend capital allocation.

Step 1 provides only the evidence and recommendation boundary required for that future role.

It does **not** yet implement the reasoning engine or call an AI provider.

## Sealed historical evidence only

`MasterAllocationAdvisoryEvidence` accepts one already verified Batch 21e historical replay through:

- `MasterHistoricalReplayAuditReport` with `VERIFIED` status;
- `MasterHistoricalReplayClosureSeal` with `SEALED` status;
- the exact `MasterHistoricalEvaluation` referenced by both artifacts.

The evidence constructor re-hashes the audit, closure and evaluation payloads instead of
trusting their stored fingerprints.

It also verifies the exact chain:

`audit -> closure -> replay result identity -> evaluation`.

A forged, cross-portfolio or mismatched evidence chain fails closed.

## Regime metadata

Evidence may optionally carry an explicit `regime_label` and `regime_source_ref`.

The two values must be supplied together. Step 1 never infers a regime from returns, PnL or market
prices.

This allows later Batch 21f steps to compare sealed runs by explicit regime provenance without
inventing classification data.

## Current policy remains the operator-owned truth

`MasterAllocationAdvisoryReport.current_allocation_policy` holds the exact existing
`MasterAllocationPolicy`.

The report re-hashes that policy before accepting it. The policy object is never replaced,
modified or reconstructed by Step 1.

A recommendation is not a `MasterAllocationPolicy`. It has:

- no `policy_id`;
- no operator-configuration source authority;
- no reservation authority;
- no admission authority;
- no Risk authority;
- no execution authority.

## Recommendation actions

Step 1 defines three explicit actions:

- `KEEP_CURRENT`;
- `PROPOSE_CHANGE`;
- `ABSTAIN`.

`KEEP_CURRENT` must reproduce the current configured envelopes exactly.

`PROPOSE_CHANGE` must provide one complete configured envelope for every existing crew and at
least one value must actually differ from the current policy.

`ABSTAIN` cannot contain proposed envelopes.

This prevents an advisory record from becoming an ambiguous partial patch.

## No membership mutation

A non-abstaining recommendation must preserve the exact current crew membership.

Batch 21f Step 1 cannot:

- add a crew;
- remove a crew;
- recruit an agent;
- promote an agent;
- mutate `AgentRegistry`.

Population changes remain governed by their existing dedicated mechanisms.

## No invented production values

If the current allocation policy is `NOT_CONFIGURED`, Step 1 requires `ABSTAIN`.

It cannot fill missing capital, risk or gross-exposure ceilings from historical performance.

This preserves the project rule that production numeric values absent from configuration remain
operator-owned or explicitly unavailable.

## Evidence-free behavior

A report with no sealed evidence may exist only as `ABSTAIN`.

This gives the future Master Professor an auditable fail-closed answer such as
`NO_SEALED_EVIDENCE` without fabricating a recommendation.

Any `KEEP_CURRENT` or `PROPOSE_CHANGE` report requires at least one sealed evidence item.

## Multi-regime evidence

Several evidence records may be attached to one report when they:

- target the same Master Portfolio;
- contain the same crew membership as the current policy;
- have unique evidence fingerprints.

Evidence is ordered deterministically by historical seal time and evidence ID.

Step 1 does not aggregate or score those runs. That belongs to a later evaluator / Master Professor
step.

## Master Professor SHADOW boundary

`MasterAllocationAdvisoryRecommendation` and `MasterAllocationAdvisoryReport` expose:

- `advisor_role = MASTER_PROFESSOR`;
- `mode = SHADOW`;
- `advisory_only = True`;
- `operator_review_required = True`;
- `auto_apply = False`;
- `policy_mutation = False`.

The report additionally exposes false authority flags for:

- dynamic allocation;
- reservation mutation;
- deterministic Risk;
- Master admission;
- local-Risk override;
- resizing;
- registry mutation;
- broker execution;
- LIVE execution;
- auto-execution.

These are structural invariants, not prompt instructions.

## Determinism

The evidence, recommendation and report contracts use stable SHA-256 fingerprints.

No wall-clock timestamp is introduced by Step 1. `evidence_through` is the maximum sealed historical
evidence timestamp, or `None` for an evidence-free abstention.

Rebuilding the same evidence and recommendation produces the same fingerprints.

## Contracts

Step 1 adds:

- `MasterAllocationAdvisoryAction`;
- `MasterAllocationAdvisoryStatus`;
- `MasterAllocationAdvisoryEvidenceSource`;
- `MasterAllocationAdvisoryEvidence`;
- `MasterAllocationAdvisoryRecommendation`;
- `MasterAllocationAdvisoryReport`;
- `build_master_allocation_advisory_evidence()`;
- `build_master_allocation_advisory_recommendation()`;
- `build_master_allocation_advisory_report()`.

## Explicit Step 1 boundary

Step 1 does not:

- rank crews;
- calculate an optimal allocation;
- introduce a scoring formula;
- infer Kelly fractions;
- infer statistical correlation;
- define promotion thresholds;
- call an AI provider;
- call the AI Gateway;
- execute recommendations;
- mutate allocation policy;
- touch PAPER positions;
- touch LIVE.

A later Batch 21f step can use these contracts to connect sealed evidence to a Master Professor
SHADOW reasoning path while keeping the generated recommendation behind explicit operator review.

## Validation in generation harness

- Step 1 targeted tests: 32 passed;
- reconstructed `tests/portfolio`: 593 passed;
- Python compilation: passed;
- public `app.portfolio` imports: passed;
- Python source/test line length <= 100: passed.

The generation harness does not contain Ruff and is not the complete repository checkout. Run Ruff,
targeted Step 1 tests, all Portfolio tests and the complete repository suite in the real checkout
before commit.
