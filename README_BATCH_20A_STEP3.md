# Batch 20a — Step 3 — Task Force gates

## Objectif

Ajouter des garde-fous déterministes avant toute exécution Task Force, sans lancer d'agent.

Le Step 3 fournit deux niveaux :

1. `evaluate_task_force_plan()` : population, fréquence, composition, états, Core allowlist,
   couverture rôles/capacités, red-team, budgets et limites d'appels ;
2. `evaluate_task_force_compute()` : contrôle d'une charge IA prospective contre le budget
   et les limites d'appels propres à la Task Force.

## Invariants

- aucun seuil de production n'est inventé ;
- `ALLOW` n'exécute rien ;
- aucun `AgentRegistry` n'est muté ;
- aucun `AgentState` n'est changé ;
- aucun Risk Engine ou broker LIVE n'est importé ;
- la gate compute Task Force ne remplace pas le hard budget `AIBudgetLedger` de l'AI Gateway ;
- les fingerprints request/policy/composition sont revalidés fail-closed ;
- un Core agent doit être explicitement autorisé par `allowed_core_agent_ids`.

## Fichiers

- `app/task_force/gates.py`
- `app/task_force/__init__.py`
- `tests/task_force/test_task_force_gates.py`

## Validation

```powershell
uv run pytest -q tests/task_force/test_task_force_gates.py
uv run pytest -q
```

Aucun commit/push n'est requis avant validation locale.
