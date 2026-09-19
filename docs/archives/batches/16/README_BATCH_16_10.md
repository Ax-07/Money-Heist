# Money Heist — Batch 16.10 v2 Dataset-aware defaults + Test rapide

À appliquer après **Batch 16.9**.

Cette v2 remplace le premier ZIP Batch 16.10.

## Defaults dataset

- symbole : `BTC/USDC`
- timeframe : `1h`
- source : `binance_spot_csv`
- intervalle : inféré du timeframe

Le nom du CSV peut aussi renseigner automatiquement ces champs lorsqu'il contient
des motifs tels que `BTCUSDC`, `BTC_USDC`, `1h`, `h1`, `60m` ou `binance`.

## Contraintes d'ordre préremplies

Preset versionné Binance Spot BTC/USDC :

```text
qty_step      = 0.00001 BTC
min_qty       = 0.00001 BTC
min_notional  = 5 USDC
max_qty       = 9000 BTC
max_leverage  = 1
```

Les valeurs restent éditables.

## Un seul bouton Test rapide

Le bouton **Test rapide** configure d'un clic les trois périodes :

```text
DESIGN / VALIDATION / OOS
```

Il travaille exclusivement avec les indices de bougies du dataset prévisualisé.

Fenêtre :

```text
720 dernières bougies maximum
```

Découpage :

```text
DESIGN       60 %
VALIDATION   20 %
OOS          20 %
```

Sur BTC/USDC en 1h avec au moins 720 bougies :

```text
DESIGN       432 bougies = 18 jours
VALIDATION   144 bougies = 6 jours
OOS          144 bougies = 6 jours
TOTAL        720 bougies = 30 jours
```

Si le fichier contient moins de 720 bougies, le bouton utilise toute la plage
disponible avec le même découpage.

**Le bouton ne lance pas le backtest.** Il règle seulement la timeline.

## Installation

Extraire le ZIP à la racine puis :

```powershell
uv run python apply_batch_16_10_dataset_aware_defaults.py
uv run pytest -q tests/dashboard/test_backtest_defaults.py
uv run pytest -q tests/dashboard
uv run pytest -q
```

Le script accepte aussi le cas où le premier Batch 16.10 a déjà été appliqué :
il ajoute alors seulement ce qui manque.

## Production modifiée

Uniquement :

```text
app/dashboard/static/backtest.html
app/dashboard/static/backtest.js
```

Pas de modification du backend, Risk Engine, PaperBroker, pipeline ou LIVE.
