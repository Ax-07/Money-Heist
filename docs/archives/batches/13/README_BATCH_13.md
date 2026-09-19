# Money Heist — Batch 13 — Exchange Adapter PAPER / Market Data réel

Le Batch 13 ajoute un adaptateur **Kraken Spot public** strictement Market Data et une frontière explicite vers le Feature Engine / Scanner existants.

```text
Kraken public REST
→ transport public sans auth
→ KrakenPublicMarketDataProvider
→ MarketSnapshot / Candle / SymbolMetadata
→ validation qualité / fraîcheur
→ Feature Engine existant
→ Scanner existant
→ opportunité compatible PAPER/SHADOW
```

Aucun ordre réel n'est possible depuis ce package.

## Principales surfaces

- `StdlibJsonTransport` ;
- `ResilientPublicHttpClient` ;
- `KrakenPublicMarketDataProvider` ;
- `SymbolMetadata` ;
- `PaperShadowMarketFeed`.

Les timeframes et seuils de fraîcheur sont volontairement **sans valeur métier par défaut** dans `KrakenAdapterConfig` : le caller doit les fournir explicitement.

Le client réseau possède seulement des valeurs techniques bornées de timeout/retry/backoff/pacing ; elles ne changent aucune règle de trading ou de risque.

Voir `DECISION_BATCH_13_EXCHANGE.md` et `INTEGRATION_BATCH_13.md`.
