# Batch 20d — Step 2 — Result Bridge into Main Orchestration

Ce Step branche un `TaskForceReport` Batch 20c déjà produit dans la finalisation du
Professor, sans exécuter de Task Force depuis le pipeline principal et sans modifier
Palermo, le Risk Engine, le broker PAPER ou les gates LIVE.

## Fichiers ajoutés

- `app/services/orchestration/task_force_report.py`
- `tests/orchestration/test_task_force_report.py`
- `tests/orchestration/test_task_force_report_pipeline_integration.py`
- `apply_batch_20d_step2.py`

## Fichiers suivis modifiés par l'apply script

- `app/agents/core.py`
- `app/services/orchestration/pipeline.py`

L'apply script vérifie les ancres exactes avant écriture, préserve CRLF/LF et est
idempotent.

## Contrat d'intégration

Un rapport Task Force est accepté uniquement s'il :

- cible le même `system_id` et le même `opportunity_id` ;
- est explicitement opportunity-scoped ;
- correspond au même snapshot/symbole/timeframe déjà validé par le pipeline ;
- ne précède ni l'opportunité ni le snapshot marché ;
- ne vient pas du futur ;
- est consommé avant expiration de l'opportunité ;
- possède un fingerprint Batch 20c recomputable et intact.

Le rapport validé est ajouté uniquement au payload `Professor.finalize_with_schema`
sous la clé `task_force_report`. Le payload historique reste strictement inchangé si
aucun rapport n'est fourni.

Le grounding final accepte alors explicitement des chemins comme :

`task_force_report.findings.0.summary`

mais uniquement si un rapport validé est réellement présent.

## Frontières conservées

- aucune création directe de `TradeProposal` par la Task Force ;
- aucun accès Task Force au Risk Engine ;
- aucun accès broker/exchange ;
- aucun changement de `AgentRegistry` ;
- Palermo principal reste inchangé et continue son propre Red Team ;
- le rapport reste advisory-only.

## Application

Depuis la racine du dépôt :

```powershell
uv run python apply_batch_20d_step2.py
```

Puis :

```powershell
uv run pytest -q tests/orchestration/test_task_force_report.py tests/orchestration/test_task_force_report_pipeline_integration.py
uv run pytest -q
```
