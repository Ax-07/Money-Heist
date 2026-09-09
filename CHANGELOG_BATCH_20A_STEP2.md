# Changelog — Batch 20a Step 2

## Added

- `app/task_force/lifecycle.py`
  - `TaskForceLifecycleAction`
  - `TaskForceLifecycleRecord`
  - `TaskForceTransitionPlan`
  - `start_task_force_lifecycle()`
  - `plan_task_force_transition()`
  - `record_task_force_transition()`
- tests lifecycle ciblés.

## Updated

- `app/task_force/__init__.py` pour exposer les contrats Step 2 tout en conservant les exports Step 1.

## Invariants

- approval d'exécution explicitement opérateur-gatée ;
- runtime sans autorité Risk/LIVE ;
- aucune mutation d'agent ou de registry ;
- aucune exécution de membre ;
- terminal states non réouvrables dans ce step ;
- révisions/fingerprints fail-closed contre les transitions stale.
