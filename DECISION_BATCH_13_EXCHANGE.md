# Batch 13 — Décision d'exchange initial

**Date :** 2026-09-07  
**Décision :** Kraken Spot — API REST publique — paires EUR  
**Statut :** ACCEPTED pour le Market Data du Batch 13

## Décision

Le premier adaptateur de données réelles Money Heist cible **Kraken Spot** via ses endpoints REST publics, sans authentification, avec les symboles canoniques :

- `BTC/EUR` ;
- `ETH/EUR` ;
- `SOL/EUR`.

Cette décision ne crée aucune capacité LIVE. Elle ne crée ni clé API, ni méthode d'ordre, ni permission de trading ou de retrait.

## Pourquoi Kraken pour ce prototype

1. `AssetPairs` est public et fournit directement les informations nécessaires à la normalisation des contraintes de marché : `pair_decimals`, `lot_decimals`, `ordermin`, `costmin`, `tick_size` et `status`.
2. `assetVersion=1` permet d'utiliser les noms d'affichage canoniques (`BTC/EUR`) au lieu des identifiants historiques internes Kraken.
3. `OHLC` est public et documente explicitement que sa dernière ligne correspond à la bougie courante non encore validée ; l'adaptateur la marque donc `is_closed=False`.
4. `Trades` est public et chaque trade inclut un timestamp. Money Heist utilise le dernier trade horodaté comme prix courant afin de disposer d'une vraie source de fraîcheur. Le ticker Kraken n'est volontairement pas utilisé comme source de `observed_at`.
5. L'usage de paires EUR est cohérent avec le prototype dont le capital réel de référence est exprimé en euros et évite d'introduire un stablecoin uniquement pour le premier connecteur Market Data.
6. Aucun SDK exchange supplémentaire n'est requis : le transport HTTP utilise uniquement la bibliothèque standard Python.

## Mapping vers Money Heist

| Kraken | Modèle interne |
|---|---|
| dernier trade `price` | `CurrentPrice.price` puis `MarketSnapshot.last_price` |
| timestamp du dernier trade | `MarketSnapshot.observed_at` |
| OHLC | `Candle` |
| dernière ligne OHLC | `Candle.is_closed=False` |
| `tick_size` | `SymbolMetadata.tick_size` |
| `lot_decimals` | `SymbolMetadata.quantity_precision` + `qty_step` dérivé exactement |
| `pair_decimals` | `SymbolMetadata.price_precision` |
| `ordermin` | `SymbolMetadata.min_qty` |
| `costmin` | `SymbolMetadata.min_notional` |
| `status` | garde-fou de disponibilité du symbole |

La projection vers le `MarketConstraints` Batch 05 ne transmet que `qty_step`, `min_qty` et `min_notional`. Les champs constitutionnels non fournis par cette source restent `None`. Le Risk Engine n'est pas modifié.

## Fraîcheur et fail-safe

Les timeframes et le seuil numérique de fraîcheur **ne sont pas figés par ce batch**. Ils doivent être injectés explicitement via `KrakenAdapterConfig` / `FreshnessPolicy`.

Le flux est rejeté avant PAPER/SHADOW si notamment :

- le dernier trade est stale ;
- le timestamp source est incohérent ;
- la bougie courante OHLC ne couvre plus le moment de réception ;
- la série OHLC comporte un trou ou une incohérence ;
- une métadonnée requise manque ;
- le symbole n'est pas `online` ;
- la réponse Kraken est invalide ;
- le réseau ou l'API restent indisponibles après les retries bornés.

## Rate limiting

Le client public applique un pacing local, des timeouts et des retries bornés avec backoff. Les réponses HTTP `429` et les erreurs serveur `5xx` sont traitées de façon fail-safe. Les erreurs Kraken de rate limit/throttling sont reconnues et remontées explicitement ; aucune boucle de retry illimitée n'existe.

## Alternatives considérées

**Binance Spot** a été considérée pour la richesse de ses métadonnées publiques et de ses filtres de symboles. Elle reste un candidat naturel pour un adaptateur ultérieur. Kraken est retenu en premier car son API publique couvre le besoin du Batch 13 avec des paires EUR, des métadonnées directement exploitables et sans dépendance SDK/authentification.

L'architecture reste exchange-agnostique : ajouter un second adaptateur ne doit pas exposer son JSON brut au domaine.

## Hors décision

Cette ADR ne décide pas :

- l'activation LIVE ;
- le futur Live Broker ;
- les permissions d'une éventuelle clé API ;
- les valeurs de risque Balanced/Conservative/Aggressive ;
- le levier ;
- les timeframes de production ;
- les seuils numériques de fraîcheur de production ;
- Rio, Denver, Recruitment Engine ou les Batchs 14+.

## Références officielles Kraken consultées

- AssetPairs : https://docs.kraken.com/api-reference/market-data/get-tradable-asset-pairs
- OHLC : https://docs.kraken.com/api-reference/market-data/get-ohlc-data
- Recent Trades : https://docs.kraken.com/api-reference/market-data/get-recent-trades
- Spot REST rate limits : https://docs.kraken.com/exchange/guides/rest/ratelimits
