# CHANGELOG — Batch 19a Step 1

## Added

- `app/recruitment/models.py`
  - `RecruitmentCandidateState` séparé de `AgentState` ;
  - `RecruitmentProposal` advisory-only ;
  - `RecruitmentBaselineSpec` ;
  - `RecruitmentSuccessCriterion` OOS et prédéfini ;
  - `RecruitmentCandidateSpec` sans autorité LIVE, sans auto-register, sans auto-promotion ;
  - constructeur pur `specify_recruitment_candidate()`.
- API publique `app/recruitment/__init__.py`.
- tests ciblés des invariants et frontières.

## Explicitly not included

- aucune mutation d'`AgentRegistry` ;
- aucune modification d'`AgentState` ;
- aucune intégration Risk Engine ;
- aucune capacité LIVE ;
- aucune campagne de replay/backtest ;
- aucun scoring Recruitment parallèle au Batch 18 ;
- aucune décision de promotion/rejet appliquée automatiquement.
