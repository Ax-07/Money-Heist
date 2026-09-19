# Batch 16.11 — Advanced Specialist Smoke Validation

Ce batch ne modifie **aucun moteur de trading**. Il ajoute un harness opérateur pour
valider immédiatement les deux spécialistes avancés avec leurs vraies frontières
de données.

## Denver

Le smoke Denver réutilise le vrai pipeline backtest, puis construit le catalogue
existant :

- `HistoricalSetupStatsCatalog`
- `catalog_from_historical_runs`
- `DenverSetupStatsContextProvider`

Les statistiques proviennent donc des opportunités exécutées et des trades
historiques fermés du replay PAPER. Aucun edge n'est inventé.

Le harness interroge ensuite le catalogue à un `as_of` postérieur à la clôture du
trade retenu et valide un vrai `DenverContext`, puis le contrat structuré
`DenverAnalysis`.

## Rio

Le smoke Rio est séparé du replay historique : utiliser une observation de marché
du 11 septembre 2026 pour une décision historique de juillet/août 2026 serait du
look-ahead.

Il lit donc uniquement les analytics **publiques et non authentifiées** de Kraken
Futures au moment du test, via les composants existants :

- `StdlibJsonTransport`
- `ResilientPublicHttpClient`
- `KrakenFuturesAnalyticsProvider`
- `KrakenFuturesRioContextProvider`

Il valide ensuite `RioContext -> RioAnalysis`.

Aucun compte exchange, aucune clé API, aucun ordre, aucun Risk Engine LIVE.

Pour BTC/USDC, le smoke mappe explicitement le contexte BTC vers `PF_XBTUSD`, de la
même manière que l'adaptateur existant utilise ce future BTC/USD comme proxy de
positionnement pour les paires spot BTC prises en charge.

## Installation

Extraire à la racine du repo puis :

```powershell
uv run pytest -q tests/backtest/test_advanced_specialist_smokes.py
uv run pytest -q
```

## Exécution

Utiliser le même CSV que dans le dashboard :

```powershell
uv run python run_advanced_specialist_smokes.py --csv "CHEMIN\VERS\BTCUSDC_1H.csv"
```

Pour tester Denver sans réseau :

```powershell
uv run python run_advanced_specialist_smokes.py --csv "CHEMIN\VERS\BTCUSDC_1H.csv" --skip-rio-live
```

Résultat attendu en fin de sections :

```text
DENVER_SMOKE=PASS
RIO_SMOKE=PASS
```

Si Denver indique qu'aucun trade fermé attribuable n'existe dans la fenêtre
rapide, cela signifie que les données sont insuffisantes pour produire un contexte
Denver honnête ; le harness refuse alors d'en inventer un.

Si Kraken est indisponible ou renvoie des données insuffisantes, Rio échoue fermé
et n'invente pas de contexte.
