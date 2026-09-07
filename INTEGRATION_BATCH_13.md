# Intégration — Batch 13 — Exchange Adapter PAPER / Market Data réel

## 1. Baseline requise

Le lot cible exactement :

```text
703e322e105b870a1c99333569638094d550ffaa
feat(dashboard): complete Batch 12 Dashboard V1
```

La baseline attendue contient **312 tests**.

## 2. Extraction

Extraire `money-heist_batch_13_exchange-adapter-paper-market-data-reel.zip` directement dans :

```text
E:\0 money heist
```

Le ZIP ne contient pas de dossier englobant : les chemins `app/...`, `tests/...`, `docs/...` et les fichiers de batch se placent directement à la racine du dépôt.

## 3. Installation et validation par défaut

```powershell
cd "E:\0 money heist"
uv sync
uv run pytest -q
```

Résultat attendu si la baseline Batch 12 est intacte :

```text
374 passed, 1 skipped
```

Le test ignoré par défaut est le smoke test réseau Kraken. Les tests unitaires utilisent exclusivement des transports fakes.

## 4. Test réseau Kraken optionnel

Ce test effectue uniquement des **GET publics** Market Data. Aucune clé API n'est utilisée.

```powershell
$env:MONEY_HEIST_RUN_NETWORK_TESTS="1"
uv run pytest -q tests/integration_network/test_kraken_public.py
Remove-Item Env:MONEY_HEIST_RUN_NETWORK_TESTS
```

Si Internet, DNS ou Kraken sont indisponibles, ce test peut naturellement échouer ; il n'est pas inclus dans la validation déterministe obligatoire.

## 5. Construction de l'adaptateur

Le Batch 13 ne choisit pas les timeframes de production ni un seuil numérique de fraîcheur à votre place. L'application doit injecter explicitement :

- un `FreshnessPolicy` ;
- les `snapshot_timeframes` ;
- la durée maximale de cache des métadonnées.

Exemple de forme d'intégration, avec les valeurs fournies par votre configuration applicative :

```python
from app.market.exchange import (
    KrakenAdapterConfig,
    KrakenPublicMarketDataProvider,
    ResilientPublicHttpClient,
    StdlibJsonTransport,
)

client = ResilientPublicHttpClient(StdlibJsonTransport())
adapter = KrakenPublicMarketDataProvider(
    client,
    config=KrakenAdapterConfig(
        freshness_policy=freshness_policy,
        snapshot_timeframes=configured_timeframes,
        metadata_max_age=configured_metadata_max_age,
    ),
)
```

## 6. Métadonnées et contraintes PAPER/SHADOW

Le premier appel `get_snapshot(symbol)` rafraîchit les métadonnées si nécessaire. Ensuite, le port synchrone existant peut lire la projection :

```python
snapshot = await adapter.get_snapshot("BTC/EUR")
constraints = adapter.get_market_constraints(symbol="BTC/EUR")
```

`constraints` vaut `None` si les métadonnées sont absentes, stale ou si le symbole n'est pas `online`. Le pipeline existant conserve alors son comportement fail-closed.

Le Risk Engine n'est jamais appelé par l'adaptateur.

## 7. Alimentation Feature Engine / Scanner

`PaperShadowMarketFeed` fournit une frontière explicite, sans broker :

```python
from app.market.exchange import PaperShadowMarketFeed

feed = PaperShadowMarketFeed(
    adapter,
    feature_engine=feature_engine,
    scanner=scanner,
    root_system_id=root_system_id,
)

market_input = await feed.build(
    symbol="BTC/EUR",
    timeframe=configured_timeframe,
    previous_market_context=previous_feature_snapshot,
)
```

Le résultat expose :

- `market_input.market_snapshot` ;
- `market_input.market_context` (`FeatureSnapshot`) ;
- `market_input.scan_result` ;
- `market_input.opportunity` si le Scanner en produit une.

Le caller décide ensuite explicitement de transmettre l'opportunité et `market_context` au runner PAPER/SHADOW existant. Le feed ne dispose d'aucune référence au Risk Engine, au Paper Broker, au Dashboard ou à un Live Broker.

## 8. Choix Kraken

La décision complète est dans `DECISION_BATCH_13_EXCHANGE.md` et ADR-019 de `docs/10_DECISIONS_ET_CHANGELOG.md`.

Le prix courant provient volontairement du dernier trade horodaté. Cela évite d'inventer un timestamp de fraîcheur pour un ticker qui n'en fournit pas.

## 9. Aucun secret

Le lot n'ajoute :

- aucune clé API ;
- aucun `.env` secret ;
- aucun header d'authentification ;
- aucun endpoint privé ;
- aucun ordre ;
- aucun droit de retrait.
