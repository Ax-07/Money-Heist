# CHANGELOG — Batch 13 — Exchange Adapter PAPER / Market Data réel

**Date :** 2026-09-07  
**Baseline Git :** `703e322e105b870a1c99333569638094d550ffaa`  
**Baseline tests :** 312  
**Tests Batch 13 hors réseau :** 62  
**Test réseau opt-in :** 1  
**Total attendu par défaut :** 374 passed, 1 skipped

## Décision d'architecture

- exchange Market Data initial : **Kraken Spot public REST** ;
- quote initiale : **EUR** ;
- univers initial : `BTC/EUR`, `ETH/EUR`, `SOL/EUR` ;
- aucune authentification ni capacité d'ordre ;
- `OPEN-004` documentée comme résolue pour le Market Data initial via ADR-019 ;
- la décision finale spot/dérivés pour le LIVE reste hors Batch 13.

## Ajouté

### Couche exchange publique

- package `app.market.exchange` séparant strictement payload HTTP/exchange et modèles métier ;
- transport JSON HTTPS basé uniquement sur la bibliothèque standard ;
- timeout explicite ;
- pacing local ;
- retries bornés ;
- backoff exponentiel borné ;
- prise en compte de `Retry-After` ;
- classification réseau / HTTP / rate limit / payload invalide ;
- aucun header d'authentification ni support de secret.

### Adaptateur Kraken Spot

- lecture `AssetPairs` ;
- lecture `Trades` avec `count=1` pour obtenir un prix **horodaté** ;
- lecture `OHLC` ;
- symboles canoniques avec `assetVersion=1` ;
- timestamps UTC ;
- `Decimal` pour prix, quantités et contraintes ;
- dernière bougie Kraken marquée `is_closed=False` ;
- validation du caractère courant de la bougie ouverte ;
- métadonnées symbole normalisées : tick size, step size, min qty, min notional, précisions, statut ;
- cache de métadonnées borné par une durée explicitement injectée ;
- projection vers le `MarketConstraints` existant sans modifier le Risk Engine ;
- données stale, incomplètes, incohérentes ou symbole non online => fail closed.

### Frontière PAPER/SHADOW

- `PaperShadowMarketFeed` :
  - obtient un `MarketSnapshot` réel via le port existant ;
  - passe ses candles au Feature Engine existant ;
  - passe le `FeatureSnapshot` au Scanner déterministe existant ;
  - retourne le contexte et l'opportunité sans appeler Risk Engine, broker ou orchestration ;
- le passage dans le pipeline PAPER/SHADOW reste un acte explicite du caller.

### Tests

- 62 tests hors réseau couvrent transport, retries, backoff, pacing, normalisation, métadonnées, contraintes, timestamps, stale data, OHLC, erreurs Kraken et frontière PAPER/SHADOW ;
- 1 smoke test réseau séparé sous `tests/integration_network/`, ignoré par défaut ;
- fakes injectables : aucun test unitaire ne dépend d'Internet.

## Documentation

- `DECISION_BATCH_13_EXCHANGE.md` ;
- `INTEGRATION_BATCH_13.md` ;
- `README_BATCH_13.md` ;
- `MANIFEST_BATCH_13.txt` ;
- mise à jour de `docs/05_MARKET_DATA_ET_EXECUTION.md` ;
- mise à jour de `docs/10_DECISIONS_ET_CHANGELOG.md` avec ADR-019.

## Non modifié intentionnellement

- Risk Engine et ses modèles ;
- profils Conservative / Balanced / Aggressive ;
- Paper Broker ;
- orchestration IA ;
- systèmes SHADOW ;
- Dashboard V1 ;
- SelfFundingRatio et logique Evaluation.

## Hors périmètre maintenu

- ordres réels ;
- Live Broker ;
- clé API exchange ;
- authentification exchange ;
- retrait ;
- réconciliation d'ordres LIVE ;
- WebSocket temps réel ;
- Rio / Denver ;
- Recruitment Engine ;
- Batchs 14+.

## Dépendances / migrations / secrets

- nouvelle dépendance Python : **aucune** ;
- migration : **aucune** ;
- secret : **aucun** ;
- variable runtime obligatoire : **aucune** ;
- variable optionnelle de test réseau : `MONEY_HEIST_RUN_NETWORK_TESTS=1`.
