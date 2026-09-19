# Batch 19b — Step 1 — Hotfix DatasetRef API

Ce hotfix corrige uniquement le test `tests/recruitment/test_recruitment_campaign_plan.py`.

## Cause

Le test initial importait `build_dataset_ref`, helper absent du contrat Batch 16 réel.
Le contrat existant expose `DatasetRef.from_candles(...)`.

## Correctif

- remplace l'import de `build_dataset_ref` par `DatasetRef` ;
- construit le dataset de test via `DatasetRef.from_candles(...)` ;
- ne modifie aucun fichier `app/services/backtest/*` ;
- ne modifie pas le code métier Recruitment ;
- ne modifie ni Risk Engine, ni AgentRegistry, ni LIVE.

Après extraction à la racine :

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
```
