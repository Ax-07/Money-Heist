# Batch 17b — Step 2 — Rio dans le feed PAPER/SHADOW

## Objectif

Brancher le cache Rio alimenté par Kraken Futures Analytics dans le chemin réel
`Market Data -> Feature Engine -> Scanner -> orchestration`, sans rendre les données
dérivées critiques pour le trading PAPER/SHADOW.

## Contrat

- le spot Kraken reste la donnée critique du feed ;
- les analytics dérivés sont rafraîchis uniquement lorsqu'un Scanner produit une opportunité ;
- une panne du sidecar dérivés ne bloque pas un input spot valide ;
- un cache Rio frais peut être réutilisé pendant un incident temporaire ;
- un cache stale n'est jamais exposé à l'orchestration ;
- le refresh réseau est terminé avant l'orchestration ;
- l'orchestration ne fait donc aucun I/O réseau pour obtenir le contexte Rio ;
- Rio n'est annoncé au Professor que si un `RioContext` utilisable existe ;
- Rio et Denver peuvent coexister via `CompositeSpecialistContextProvider` ;
- deux providers qui revendiquent le même spécialiste font échouer la composition ;
- aucune autorité broker, Risk Engine, marge, dérivés de trading ou LIVE n'est ajoutée.

## Cache / refresh

`KrakenFuturesRioContextProvider` est désormais à la fois :

1. un sidecar asynchrone de `PaperShadowMarketFeed` via `refresh_for_market(...)` ;
2. un provider synchrone de `OrchestrationPipeline` via `contexts_for(...)`.

Un `min_refresh_interval` évite de répéter les appels publics pour plusieurs opportunités
très proches. En cas d'échec attendu de l'API publique, un ancien snapshot n'est retenu
que s'il est encore frais au temps de décision.

## Diagnostics

`PaperShadowMarketInput.sidecar_refreshes` expose des statuts non critiques :

- `REFRESHED` ;
- `CACHED` ;
- `UNAVAILABLE` ;
- `FAILED`.

`FAILED` est réservé aux erreurs inattendues du sidecar ; même dans ce cas le feed spot
reste disponible. Le caller peut journaliser ces diagnostics sans les confondre avec un
échec du Risk Engine ou du broker.

## Validation

Les tests du Step 2 couvrent notamment :

- refresh uniquement lorsqu'une opportunité existe ;
- panne sidecar non bloquante ;
- cache frais conservé après panne publique temporaire ;
- cache stale rejeté ;
- cooldown de refresh ;
- composition Rio + Denver sans écrasement ;
- sélection effective de Rio par le Professor après refresh du feed.
