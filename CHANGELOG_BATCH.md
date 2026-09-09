# Batch 17b — Rio avancé / données dérivées réelles

## Pré-requis

- Batch 17a validé et commité ;
- Step 17b.1 Kraken Futures Analytics validé avec smoke réseau public ;
- Step 17b.2 intégration PAPER/SHADOW validée.

## Livré

- adaptateur public Kraken Futures Analytics ;
- mapping explicite BTC/ETH/SOL vers les perpetuals Kraken ;
- funding, open interest, variation OI et long/short ratio normalisés ;
- absence explicite du split long/short des liquidations non garanti ;
- cache Rio avec fraîcheur et cooldown ;
- refresh sidecar uniquement après opportunité Scanner ;
- panne dérivés non critique pour le flux Spot/PAPER ;
- Rio context-gated dans l'orchestration ;
- composition Rio + Denver ;
- observabilité read-only Rio ;
- documentation et ADR-027.

## Non modifié

- Risk Engine ;
- sizing ;
- PaperBroker ;
- LiveBroker ;
- kill switches ;
- authentification Kraken privée ;
- premier LIVE Kraken Spot/EUR.

## Limite volontaire

Rio n'est pas injecté dans les replays historiques Batch 16 sans dataset dérivés historique dédié.
