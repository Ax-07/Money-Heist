# Batch 21f — Step 2 — Master Professor Evidence Analysis Engine

Baseline: `2fb17ae` — Batch 21f Step 1 Master Allocation Advisory Contracts.

## Goal

Add a deterministic, descriptive evidence-analysis layer for the future Master Professor / Allocator
without creating allocation authority.

Step 2 consumes the sealed historical evidence contracts introduced by Step 1 and produces an
immutable SHADOW analysis report. It does not generate a recommendation, mutate the current
`MasterAllocationPolicy`, reserve capital, call Risk, call a broker, or touch LIVE.

The path is:

`sealed Batch 21e evidence -> Step 1 advisory evidence -> Step 2 descriptive analysis -> STOP`.

## Architectural role

The project architecture assigns the future Master Professor / Allocator three responsibilities:

- compare systems;
- analyze performance according to regimes;
- recommend capital allocation.

Step 2 implements only the first two as deterministic evidence preparation.

The third responsibility remains outside this step.

## Exact evidence boundary

`build_master_allocation_evidence_analysis()` accepts:

- the exact current `MasterAllocationPolicy`;
- one or more `MasterAllocationAdvisoryEvidence` objects from Step 1.

Before analysis, every evidence item is rebuilt through the Step 1 constructor. This revalidates:

- the Batch 21e audit;
- the Batch 21e closure seal;
- the historical evaluation fingerprint;
- the audit -> closure -> evaluation identity chain;
- Master Portfolio identity;
- exact crew membership;
- regime metadata provenance.

Post-construction tampering therefore fails closed.

The current allocation policy fingerprint is also recomputed before use.

## No invented regime classification

Step 2 never infers market regimes.

If an evidence item carries an explicit `regime_label` and `regime_source_ref`, the analysis
preserves that exact pair. Two identical labels from different source references are treated as
different regime scopes.

Unlabelled evidence remains unlabelled and is never assigned to a synthetic regime.

## Per-crew evidence observations

For every crew in every sealed evidence item, Step 2 creates one immutable
`MasterAllocationCrewEvidenceObservation` containing only
source-derived values:

- evidence identity and fingerprint;
- historical allocation-policy fingerprint;
- historical evaluation fingerprint;
- sealed timestamp;
- exact regime metadata, when supplied;
- entry / closed / open lot counts;
- win / loss / breakeven counts;
- realized net PnL;
- final open risk;
- final gross exposure;
- win rate;
- profit factor;
- expectancy.

Evaluation metrics are copied into a Portfolio-local metric contract so importing `app.portfolio`
does not implicitly import `app.evaluation`.

## Descriptive crew aggregation

Step 2 builds `MasterAllocationCrewAnalysis` records for:

- all evidence for each crew;
- each exact labelled regime provenance for each crew.

The aggregate contains:

- replay count;
- pooled trade counts;
- pooled outcome counts;
- sum of replay realized net PnL;
- mean replay realized net PnL;
- pooled win rate;
- pooled closed-lot expectancy;
- number of evidence items ending with an open logical position.

These values are descriptive replay statistics only.

`replay_realized_net_pnl_sum` is not Master capital and is never written into an allocation policy.
The contract explicitly exposes `physical_capital_aggregation = False`.

## No summing of physical or counterfactual capital

Step 2 never sums:

- source `BacktestRun.config.initial_balance` values;
- SHADOW equities;
- current allocation ceilings;
- final open-risk values from separate replays;
- final gross-exposure values from separate replays.

The one-physical-capital invariant from Batch 21 remains unchanged.

Final open-risk and gross-exposure values are preserved only on their original per-evidence
observations.

## Pairwise comparisons without ranking

For every canonical crew pair, Step 2 creates `MasterAllocationPairwiseComparison` records for:

- all common evidence;
- each exact labelled regime provenance.

The comparison reports only paired descriptive deltas:

- count of replays where left/right/tie has higher realized net PnL;
- mean paired realized-net-PnL delta;
- count of paired available win-rate comparisons;
- left/right/tie win-rate counts;
- mean paired win-rate delta when available;
- count of paired available expectancy comparisons;
- left/right/tie expectancy counts;
- mean paired expectancy delta when available.

There is deliberately no:

- winner field;
- ranking;
- composite score;
- weighting formula;
- threshold;
- promotion rule;
- allocation percentage.

This prevents Step 2 from silently becoming an optimizer.

## Metric availability

Step 2 preserves three metric states:

- `AVAILABLE`;
- `UNAVAILABLE`;
- `UNBOUNDED`.

Pairwise mean deltas for win rate or expectancy are produced only when both crew values are
numerically available for the same evidence item.

If no paired numeric sample exists, the corresponding delta is explicitly unavailable.

## Historical policy provenance

A Step 2 report records every distinct historical allocation-policy fingerprint represented by its
sealed evidence.

This is intentionally separate from the current operator-owned policy fingerprint.

If the historical evidence spans multiple policy fingerprints, the report emits:

`MULTIPLE_HISTORICAL_ALLOCATION_POLICIES`.

It does not normalize those historical policies or pretend they were identical.

## Evidence sufficiency reason codes

The report may expose descriptive reason codes such as:

- `SINGLE_EVIDENCE_ONLY`;
- `UNLABELED_EVIDENCE_PRESENT`;
- `MULTIPLE_HISTORICAL_ALLOCATION_POLICIES`;
- `AI_ECONOMICS_NOT_FULLY_AVAILABLE`.

These are provenance / sufficiency notes only. They do not cause automatic allocation actions.

## Unconfigured current allocation policy

Unlike the Step 1 recommendation contract, Step 2 may descriptively analyze evidence while the
current
allocation policy is `NOT_CONFIGURED`.

This does not fill any missing numeric ceiling and cannot create a recommendation.

Step 1 still requires advisory `ABSTAIN` when a current policy is unconfigured.

## Master Professor SHADOW boundary

`MasterAllocationEvidenceAnalysisReport` exposes structural invariants:

- `advisor_role = MASTER_PROFESSOR`;
- `mode = SHADOW`;
- `advisory_only = True`;
- `descriptive_analysis_only = True`;
- `recommendation_generated = False`;
- `allocation_generated = False`;
- `score_generated = False`;
- `ranking_generated = False`;
- `optimization_performed = False`;
- `statistical_correlation_inferred = False`;
- `kelly_sizing = False`;
- `policy_mutation = False`;
- `reservation_authority = False`;
- `risk_authority = False`;
- `admission_authority = False`;
- `local_risk_override = False`;
- `resize_authority = False`;
- `registry_mutation = False`;
- `broker_authority = False`;
- `live_authority = False`;
- `auto_execute = False`;
- `physical_capital_aggregation = False`.

These are data-contract invariants, not prompt-only instructions.

## Determinism

Evidence is canonicalized by historical seal timestamp and evidence ID.

Observations, crew analyses, regime scopes, crew pairs, reason codes and historical policy
fingerprints are deterministically ordered.

No wall-clock timestamp or random source is introduced.

Rebuilding the same analysis from the same current policy and sealed evidence yields the same
`analysis_id` and SHA-256 fingerprint.

## Contracts

Step 2 adds:

- `MasterAllocationAnalysisMetricStatus`;
- `MasterAllocationAnalysisMetric`;
- `MasterAllocationAnalysisScope`;
- `MasterAllocationCrewEvidenceObservation`;
- `MasterAllocationCrewAnalysis`;
- `MasterAllocationPairwiseComparison`;
- `MasterAllocationEvidenceAnalysisStatus`;
- `MasterAllocationEvidenceAnalysisReport`;
- `build_master_allocation_evidence_analysis()`.

## Explicit Step 2 boundary

Step 2 does not:

- ask an LLM to choose allocations;
- call an AI provider directly;
- call the AI Gateway;
- generate `MasterAllocationAdvisoryRecommendation`;
- choose `KEEP_CURRENT`, `PROPOSE_CHANGE` or `ABSTAIN`;
- generate allocation ceilings;
- rank crews;
- produce a composite score;
- infer Kelly fractions;
- infer statistical correlation;
- mutate `MasterAllocationPolicy`;
- mutate reservations;
- override local Risk;
- override Master Risk Gate admission;
- resize a Risk-authorized trade;
- mutate `AgentRegistry`;
- submit PAPER orders;
- arm or execute LIVE.

A later Step 3 can expose this deterministic analysis to a Master Professor SHADOW reasoning adapter
through the existing AI Gateway and force its output back through the Step 1 recommendation contract
and operator review boundary.

## Validation in generation harness

- Step 2 targeted tests: 24 passed;
- Step 1 + Step 2 targeted tests: 56 passed;
- reconstructed `tests/portfolio`: 617 passed;
- Python compilation: passed;
- public `app.portfolio` import: passed;
- `app.evaluation` implicit import: absent;
- Python source/test line length <= 100: passed.

The generation harness does not contain Ruff and is not the complete repository checkout. Run Ruff,
targeted Step 2 tests, all Portfolio tests and the complete repository suite in the real checkout
before commit.
