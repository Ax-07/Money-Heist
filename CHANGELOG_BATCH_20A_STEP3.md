# Changelog — Batch 20a Step 3

## Ajouts

- `TaskForceCapacitySnapshot` ;
- `TaskForcePlanGateDecision` ;
- `TaskForceComputeRequest` / `TaskForceComputeDecision` ;
- `evaluate_task_force_plan()` ;
- `evaluate_task_force_compute()` ;
- fingerprints déterministes de gate et de capacité ;
- tests population, états, Core allowlist, rôles/capacités, red-team, budget, appels,
  retries et stale fingerprints.

## Frontières conservées

- aucune exécution Task Force ;
- aucune mutation AgentRegistry ;
- aucun changement AgentState ;
- aucun import Risk Engine / broker LIVE ;
- aucun contournement du hard budget AI Gateway ;
- aucune valeur de politique inventée.
