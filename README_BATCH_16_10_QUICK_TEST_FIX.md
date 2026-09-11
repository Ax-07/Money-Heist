# Patch — Batch 16.10 Quick Test

Ce patch corrige uniquement le bouton **Test rapide** du Batch 16.10 v2.

## Nouveau comportement

```text
Warm-up features : 35 bougies
DESIGN           : 60 bougies
VALIDATION       : 20 bougies
OOS              : 20 bougies
Total test       : 100 bougies maximum
```

Sur BTC/USDC en 1h, les périodes de test couvrent environ 100 heures.

La fenêtre démarre juste après les 35 bougies de warm-up afin d'éviter de placer
le test tout au bout d'un gros fichier historique.

Si le dataset contient moins de 135 bougies mais au moins 41, toute la plage
disponible après warm-up est utilisée avec le même ratio 60/20/20.

Si le dataset contient moins de 41 bougies, le bouton refuse le preset.

Le bouton sert uniquement à tester rapidement le chemin Scanner → Professor →
spécialistes → Palermo → Risk Engine / Paper pipeline. Il ne force aucune
opportunité artificielle et ne lance pas automatiquement la campagne.

## Application

```powershell
uv run python apply_batch_16_10_quick_test_fix.py
uv run pytest -q tests/dashboard/test_backtest_defaults.py
uv run pytest -q tests/dashboard
uv run pytest -q
```
