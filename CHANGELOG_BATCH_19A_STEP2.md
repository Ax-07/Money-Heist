# CHANGELOG — Batch 19a Step 2

## Added

- `app/recruitment/lifecycle.py`
  - `RecruitmentLifecycleAction` ;
  - `RecruitmentLifecycleRecord` ;
  - `RecruitmentTransitionPlan` ;
  - machine d'états Recruitment-only ;
  - fingerprint SHA-256 déterministe des plans ;
  - `start_recruitment_lifecycle()` ;
  - `plan_recruitment_transition()` advisory/non-mutating ;
  - `record_recruitment_transition()` exigeant une autorisation opérateur explicite ;
  - protection contre les plans stale et doubles enregistrements.
- API publique Recruitment mise à jour.
- tests lifecycle et boundary dédiés.

## Preserved boundaries

- aucun ajout à `AgentState` ;
- aucune création/mutation d'`AgentRegistryEntry` ;
- aucun état `ACTIVE` / `ON_DEMAND` dans le lifecycle candidat ;
- aucune dépendance Risk Engine ou trading LIVE ;
- aucune transition automatique ;
- `PROMOTION_RECOMMENDED` reste advisory-only ;
- aucun scoring Recruitment parallèle à la réputation/ablation Batch 18.

## Explicitly deferred

- limites de population ;
- budget/frequency gates ;
- campagnes candidate-vs-baseline ;
- bridge vers `AblationComparison` et réputation Batch 18 ;
- décision advisory fondée sur preuves OOS.
