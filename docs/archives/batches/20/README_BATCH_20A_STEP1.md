# Batch 20a — Step 1 — Task Force Contracts

Baseline inspectée : `572cd07` — `feat(recruitment): complete Batch 19 Recruitment Engine`.

## Périmètre

Ce step ajoute uniquement les contrats immuables de fondation :

- `TaskForceRequest` ;
- `TaskForceOperatorPolicy` ;
- `TaskForceRegistryAgentSnapshot` ;
- `TaskForceMemberAssignment` ;
- `TaskForcePlan` ;
- états / trigger / influence scope ;
- fingerprints SHA-256 déterministes request / policy / composition ;
- constructeur pur `build_task_force_plan()`.

Il n'ajoute encore ni sélection d'agents, ni lifecycle runtime, ni gate de population/budget,
ni appels IA multi-membres, ni agrégation, ni Red Team runtime.

## Frontières conservées

- snapshot membre dérivé d'un `AgentRegistryEntry` existant ;
- aucun candidat Recruitment n'est converti en agent ;
- aucun changement d'`AgentState` ;
- aucune mutation `AgentRegistry` ;
- aucun nouvel outil accordé par la Task Force ;
- aucun import Risk Engine, PaperBroker, LIVE broker ou exchange ;
- `risk_authority=False` et `live_authority=False` ;
- `TaskForcePlan` reste `PLANNED` et nécessite une autorisation opérateur avant exécution ;
- seuils de population/compute exigés explicitement dans `TaskForceOperatorPolicy`.

## Tests ciblés

```powershell
uv run pytest -q tests/task_force/test_task_force_models.py
```

Puis, après succès :

```powershell
uv run pytest -q
git status --short
```

Aucun commit/push dans ce step.
