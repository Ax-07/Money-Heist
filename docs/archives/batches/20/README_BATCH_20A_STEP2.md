# Batch 20a — Step 2 — Task Force Lifecycle

Ce step ajoute un lifecycle propre aux Task Forces, distinct de `AgentState` et sans mutation du registre.

## Lifecycle

```text
PLANNED
→ APPROVED_FOR_EXECUTION
→ RUNNING
→ COMPLETED

ou fail-safe vers
→ BLOCKED
→ CANCELLED
→ FAILED
```

La transition `PLANNED → APPROVED_FOR_EXECUTION` exige une autorisation opérateur explicite.
Une fois cette autorisation enregistrée, les transitions runtime restent des changements du lifecycle Task Force uniquement.

## Garde-fous

- aucune mutation `AgentRegistry` ;
- aucune mutation `AgentState` ;
- aucune autorité Risk ;
- aucune autorité LIVE ;
- aucune exécution d'agent dans ce step ;
- aucun import du Risk Engine, PaperBroker, broker LIVE ou Recruitment Engine ;
- fingerprints Request/Policy/Composition conservés dans le lifecycle ;
- révision et transition ID empêchent la réutilisation silencieuse d'un plan stale ;
- une Task Force expirée ne peut plus être approuvée ni démarrée.

## Installation

Extraire le ZIP directement à la racine du dépôt.

## Validation ciblée

```powershell
uv run pytest -q tests/task_force/test_task_force_lifecycle.py
```

Puis :

```powershell
uv run pytest -q
git status --short
```

Ne pas commit/push avant validation explicite du step.
