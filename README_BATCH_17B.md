# Batch 17b — Rio avancé / données dérivées réelles

## Objectif

Activer Rio avec des données dérivés réelles sans étendre son autorité et sans modifier le premier
LIVE Kraken Spot/EUR.

## Source

Le batch utilise les analytics publics Kraken Futures, sans authentification : funding, open interest,
variation d'open interest et long/short ratio. Le split long/short des liquidations n'est pas inventé.

## Architecture

```text
Kraken Spot public → Feature Engine → Scanner
                                ↓ opportunité
                  Kraken Futures Analytics sidecar
                                ↓ cache frais
                    RioContextProvider → Rio
```

Le sidecar est non critique pour le flux spot. Une indisponibilité dérivés retire Rio de la crew si
aucun cache frais n'existe, mais ne bloque pas PAPER/SHADOW.

## Observabilité

`RioContextDiagnostic` expose sans I/O supplémentaire :
- `REFRESHED` ;
- `CACHE_HIT` ;
- `DEGRADED` ;
- `STALE` ;
- `UNAVAILABLE`.

Ces diagnostics n'entrent ni dans le prompt de Rio, ni dans le Risk Engine.

## Limite historique

Les analytics live ne sont pas rétroinjectés dans Batch 16. Un backtest Rio futur exigera un dataset
historique dérivés horodaté et reproductible.

## Sécurité

Aucun secret, aucune API privée Futures, aucun broker, aucune marge, aucun levier et aucune capacité
d'ordre ne sont ajoutés par ce batch.
