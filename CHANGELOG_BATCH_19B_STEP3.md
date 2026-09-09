# CHANGELOG — Batch 19b Step 3

## Added
- `app/recruitment/evidence_gate.py`
  - `RecruitmentEvidencePurpose`
  - `RecruitmentEvidenceBasis`
  - `RecruitmentEvidenceProvenance`
  - `RecruitmentEvidenceGateDecision`
  - `evaluate_recruitment_evidence`
- tests de comparabilite, provenance, OOS et boundaries.

## Updated
- `app/recruitment/__init__.py` pour exporter les nouveaux contrats.

## Safety / authority
- advisory/audit only ;
- aucune evaluation des seuils de succes ;
- aucune promotion ;
- aucune mutation AgentRegistry ;
- aucun LIVE ;
- aucune modification du Risk Engine.
