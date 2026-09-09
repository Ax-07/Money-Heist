# Changelog — Batch 19c Step 2

## Ajouté

- `app/recruitment/candidate_reputation.py`
  - `RecruitmentCandidateReputationDimensions`
  - `RecruitmentCandidateCostEvidence`
  - `RecruitmentCandidateReputationEvidenceReport`
  - `RecruitmentReputationBasis`
  - `RecruitmentCostEvidenceBasis`
  - `build_candidate_reputation_evidence(...)`
- exports publics Recruitment associés ;
- tests de réutilisation `aggregate_ablation(...)` / `build_agent_reputation(...)` ;
- tests de distinction coût direct candidat / coût marginal système ;
- tests de cohérence Evaluation ↔ PeriodReport ↔ AblationComparison ;
- tests de budget dépassé enregistré sans auto-action ;
- tests DIAGNOSTIC non-OOS ;
- tests de bridge stale ;
- tests AST de boundary contre Registry/Risk/LIVE/state advisory.

## Invariants

- aucune évaluation des success criteria dans ce step ;
- aucun score unique de recrutement ;
- aucune recommandation de lifecycle/promotion ;
- aucun `AgentState` exposé dans le contrat Recruitment réputationnel ;
- coût direct candidat distinct du coût IA marginal total ;
- nature estimée/simulée des coûts explicitement conservée ;
- aucune mutation AgentRegistry ;
- aucune action LIVE ;
- aucun changement Risk Engine.
