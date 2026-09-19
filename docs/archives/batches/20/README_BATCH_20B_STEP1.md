# Batch 20b — Step 1 — Dynamic Composition & Reputation

Ce step ajoute une composition déterministe des Task Forces à partir du `AgentRegistry`
existant et des évidences multidimensionnelles Batch 18.

## Principes

- aucun registry parallèle ;
- aucune mutation `AgentRegistry` / `AgentState` ;
- aucun candidat Batch 19 hors registry ne peut être sélectionné ;
- capacités explicitement fournies, jamais inventées ;
- états filtrés par `TaskForceOperatorPolicy` ;
- Core agents utilisables uniquement via allowlist explicite ;
- réputation conservée par dimensions, sans score pondéré global ;
- ordre des dimensions de réputation explicitement fourni par la policy ;
- tie-break final déterministe par `agent_id` ;
- aucune exécution, aucun Risk Engine, aucun broker LIVE.

Le résultat de composition reste advisory-only et expose explicitement
`aggregate_reputation_score = None`.

## Validation

```powershell
uv run pytest -q tests/task_force/test_task_force_composition.py
uv run pytest -q
```
