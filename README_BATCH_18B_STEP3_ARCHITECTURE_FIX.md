# Batch 18b — Step 3 — Architecture hotfix

Le test global `tests/evaluation/test_boundaries.py` a correctement détecté que le premier Step 3
plaçait un factory d'exécution PAPER/Risk dans `app/evaluation`.

## Correction

- le factory concret est déplacé vers `app/services/backtest/ablation_runtime.py` ;
- le test Step 3 importe désormais ce module ;
- l'ancien `app/evaluation/ablation_campaign_runtime.py` devient un tombstone sans dépendance Risk ;
- aucune logique métier du factory n'est modifiée ;
- aucune nouvelle dépendance Python n'est ajoutée.

## Frontière restaurée

`app/evaluation` conserve uniquement la planification, l'attribution, les comparaisons,
la réputation et l'advisory. L'assemblage Replay + PaperBroker + Risk Engine appartient à
`app/services/backtest`.

## Validation

```powershell
uv run pytest -q tests/evaluation/test_ablation_campaign_runtime.py tests/evaluation/test_boundaries.py
uv run pytest -q
```

Le tombstone sera supprimé lors de la clôture Batch 18b, avant le commit final.
