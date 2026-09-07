# Money Heist — Batch 02 Market Data Core

## Objectif

Ajouter la couche Market Data déterministe et exchange-agnostic par-dessus le Batch 01 validé.

## Périmètre livré

- `MarketDataProvider` sous forme de `Protocol` asynchrone ;
- `InMemoryMarketDataProvider` pour tests/replay sans exchange réel ;
- modèle normalisé `Candle` OHLCV ;
- modèle `MarketSnapshot` et `SnapshotQuality` ;
- timestamps obligatoirement timezone-aware et normalisés en UTC ;
- validation OHLCV ;
- validation chronologique et détection des doublons ;
- politique de fraîcheur configurable ;
- détection des trous de bougies quand l'intervalle attendu est fourni ;
- construction déterministe d'un snapshot avec statut qualité ;
- import historique CSV simple ;
- exemple CSV ;
- tests unitaires du Batch 02.

## Hors périmètre volontaire

- aucun exchange réel ;
- aucun websocket/REST exchange ;
- aucun indicateur technique ;
- aucun Feature Engine ;
- aucun Scanner ;
- aucune `CandidateOpportunity` ;
- aucune logique de trading ou de risque.

Ces éléments restent dans les batches prévus par la roadmap.

## Fichiers ajoutés

```text
app/market/__init__.py
app/market/models.py
app/market/provider.py
app/market/quality.py
app/market/historical.py
app/market/snapshot.py

tests/market/test_models.py
tests/market/test_quality.py
tests/market/test_historical.py
tests/market/test_provider.py

sample_data/btcusdt_1m_example.csv
CHANGELOG_BATCH.md
```

## Dépendances

Aucune nouvelle dépendance n'est requise au-delà des dépendances du Batch 01 : le code s'appuie sur Python standard + Pydantic déjà présent via le socle FastAPI.

## Intégration dans VS Code

1. Fermer le serveur de développement s'il tourne.
2. Extraire le ZIP à la racine du projet Money Heist, de façon à fusionner `app/`, `tests/` et `sample_data/`.
3. Ne pas supprimer les fichiers du Batch 01.
4. Depuis PowerShell à la racine du projet :

```powershell
uv sync
uv run pytest -q
```

Le Batch 01 comptait 11 tests validés. Ce lot ajoute 15 tests Market Data ; après intégration, la suite complète devrait donc afficher **26 tests** si le socle local n'a pas changé.

## Vérification optionnelle de l'import CSV

```powershell
uv run python -c "from datetime import timedelta; from app.market import import_candles_csv; r=import_candles_csv('sample_data/btcusdt_1m_example.csv', symbol='BTCUSDT', timeframe='1m', candle_interval=timedelta(minutes=1)); print(len(r.candles), r.quality.is_valid)"
```

Résultat attendu :

```text
3 True
```

## Compatibilité et décisions ouvertes

Le Batch 02 ne fige volontairement pas :
- l'exchange initial ;
- les paires exactes ;
- les timeframes de production.

La durée attendue d'une bougie et le seuil de fraîcheur sont donc fournis explicitement par configuration/appel, plutôt qu'encodés en dur dans les modèles.

## Critères d'acceptation du lot

- modèles normalisés indépendants de tout payload exchange ;
- données stale détectées ;
- timestamps UTC cohérents ;
- doublons rejetés ;
- trous détectés ;
- import historique reproductible ;
- aucun accès LIVE ;
- tests du lot au vert.

## Note de fusion

Le ZIP n'inclut volontairement pas `app/__init__.py`, `pyproject.toml`, la configuration FastAPI, la base SQLite ni les fichiers de bootstrap du Batch 01. Il ajoute uniquement la couche Market Data et ses tests afin de minimiser le risque de régression lors de l'extraction.
