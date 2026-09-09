# CHANGELOG — Batch 19d Step 2

## Ajouté

- `app/recruitment/advisory_transition.py`
  - `RecruitmentAdvisoryTransitionStatus` (`READY`, `BLOCKED`) ;
  - `RecruitmentAdvisoryTransitionPlan` ;
  - `plan_recruitment_advisory_transition(...)` ;
  - fingerprint déterministe du contexte capacité + plan ;
  - revalidation des fingerprints et de la lineage ;
  - mapping advisory vers lifecycle ;
  - guards SHADOW, budget et population active.
- exports publics dans `app/recruitment/__init__.py`.
- tests fonctionnels et tests de frontière dédiés.

## Garanties

- aucune transition appliquée par le planner ;
- aucune mutation `AgentRegistry` ;
- aucune promotion effective ;
- aucune autorité LIVE ;
- autorisation opérateur toujours requise ;
- `BLOCKED` ne transporte jamais de transition planifiable ;
- `REJECT` n'est pas empêché par une capacité déjà saturée.

## Validation cumulée de préparation

- `120 passed` sur `tests/recruitment` ;
- `python -m compileall` : OK.
