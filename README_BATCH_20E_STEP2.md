# Batch 20e — Step 2 — Historical Replay & Task Force Ablation

Ce lot ajoute une campagne historique déterministe `BASELINE` vs `WITH_TASK_FORCE`
ciblée sur une opportunité précise.

## Principes

- deux `BacktestRun` twins dérivés du même run source ;
- mêmes dataset, période et paramètres hors assumptions réservées Batch 20 ;
- runtime isolé par variante ;
- exécution strictement `PAPER` ;
- aucun artefact Task Force autorisé dans la baseline ;
- exactement un `TaskForceReport` + une exécution Task Force dans le treatment ;
- report/exécution liés à l'opportunité et au système rejoués ;
- timestamps Task Force contenus dans la période historique ;
- égalité stricte des `processed_candles` et `opportunity_count` ;
- comparaison économique via les contrats du Step 20e.1 ;
- aucune promotion, mutation registry, autorité Risk ou LIVE.

## Fichiers

- `app/evaluation/task_force_replay.py`
- `tests/evaluation/test_task_force_replay.py`

## Validation

```powershell
uv run pytest -q tests/evaluation/test_task_force_replay.py
uv run pytest -q
git status --short
```
