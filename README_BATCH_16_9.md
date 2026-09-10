# Money Heist — Batch 16.9 Backtest Dashboard UX

**Baseline attendue :** `6d32f5597c0a3e8d86aabe977fc02dff894048a4`

Ce lot réalise la refonte UX/UI du Backtest Dashboard sans modifier le moteur Batch 16.

## Contenu

- timeline DESIGN / VALIDATION / OOS pilotée par les indices des bougies du CSV ;
- suppression des six champs `datetime-local` ;
- compteurs de bougies et dates début/fin dérivées en direct ;
- preset 60/20/20 conservé ;
- cards agents construites depuis le registry backend ;
- Risk Engine affiché comme service déterministe ;
- halo `WORKING` pour les appels IA réellement en cours ;
- animations directionnelles reposant sur les traces auditées ;
- journal structuré conservé ;
- support `prefers-reduced-motion`.

## Installation

1. Extraire **le contenu du ZIP à la racine du dépôt Money-Heist**.
2. Vérifier que `tests/dashboard/test_backtest_ux.py` est présent.
3. Depuis la racine :

```powershell
uv run python apply_batch_16_9_backtest_dashboard_ux.py
```

Le script refuse par défaut un HEAD différent du commit de référence.

Pour une branche contenant volontairement des commits ultérieurs compatibles :

```powershell
uv run python apply_batch_16_9_backtest_dashboard_ux.py --allow-other-head
```

Les anchors restent fail-closed si les fichiers ont divergé.

## Validation

```powershell
uv run pytest -q tests/dashboard/test_backtest_ux.py
uv run pytest -q tests/dashboard
uv run pytest -q
```

## Contrôle manuel

Ouvrir `/dashboard/backtest`, charger puis prévisualiser un CSV.

La timeline doit :
- rester dans le dataset ;
- empêcher les chevauchements ;
- afficher les compteurs en direct ;
- envoyer au backend uniquement des timestamps correspondant à des bougies existantes.

Lancer ensuite une campagne MOCK :
- cards agents visibles ;
- événements récents animés ;
- communications directionnelles ;
- journal structuré toujours accessible.

En LIVE_EVAL, les appels suffisamment longs apparaissent en `WORKING`.

## Frontières conservées

Le batch ne modifie pas `HistoricalReplayRunner`, `BacktestSplitPlan`, `RiskEngine`,
`PaperBroker`, `PaperTradingPipeline` ni aucun composant LIVE.

`LIVE_EVAL` reste : **IA réelle possible + trading PAPER uniquement**.

Aucune clé fournisseur n'est ajoutée au frontend.

Le ZIP utilise `CHANGELOG_BATCH_16_9.md` afin de ne pas écraser le changelog global du dépôt.
