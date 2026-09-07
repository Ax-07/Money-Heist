# Batch 14 — Décision LIVE initial : Kraken Spot / EUR

**Date :** 2026-09-07  
**Statut :** ACCEPTED  
**Résout :** `OPEN-005 — Spot ou dérivés`

## Décision

Le premier marché visé pour le futur LIVE du prototype Money Heist est **Kraken Spot**, avec les paires canoniques déjà retenues au Batch 13 : `BTC/EUR`, `ETH/EUR`, `SOL/EUR`.

Cette décision **n'active pas le LIVE**. Le Batch 14 livre uniquement l'infrastructure sécurisée. L'activation opérationnelle et le capital réel appartiennent au Batch 15.

## Raisons

- le capital prototype de 100 € sert d'abord à valider l'exécution réelle et la sécurité ;
- l'orientation du projet est sans levier ou avec levier minimal ; le Spot permet d'éviter marge, liquidation et funding pour le premier LIVE ;
- les métadonnées et `MarketConstraints` Kraken Spot du Batch 13 sont déjà la source de vérité de marché ;
- le modèle de réconciliation Spot repose principalement sur ordres, fills et balances, sans état de marge ou de liquidation supplémentaire ;
- Kraken Spot et Kraken Derivatives ont des surfaces API et des modèles opérationnels distincts ; choisir les dérivés maintenant augmenterait la complexité, les permissions et les états à réconcilier ;
- le principe de permissions minimales favorise la surface privée Spot strictement nécessaire.

## Conséquences

- aucune valeur numérique de risque n'est fixée ici ;
- aucun profil Risk Engine n'est modifié ;
- aucun levier n'est ajouté par le Live Broker Batch 14 ;
- les ordres privés restent limités à un adaptateur Kraken Spot explicite ;
- les dérivés restent hors périmètre du premier LIVE et pourront être réévalués ultérieurement ;
- une décision `SHORT` ne doit jamais être transformée implicitement en vente à découvert à effet de levier par le broker Spot.

## Alternatives considérées

### Kraken Derivatives

Non retenu pour le premier LIVE : apporte marge, liquidation, funding, gestion de positions dérivées, API/permissions spécifiques et réconciliation plus complexe, sans nécessité démontrée pour la validation initiale du prototype.

### Spot avec marge

Non retenu pour le premier LIVE : réintroduit les risques de levier et de marge que la décision Spot cherche précisément à éviter au démarrage.

## Références Kraken consultées

- Spot REST Authentication : https://docs.kraken.com/exchange/guides/rest/authentication
- Add Order : https://docs.kraken.com/api-reference/trading/add-order
- Get Open Orders : https://docs.kraken.com/api-reference/account-data/get-open-orders
- Get Closed Orders : https://docs.kraken.com/api-reference/account-data/get-closed-orders
- Cancel Order : https://docs.kraken.com/api-reference/trading/cancel-order
- Get API Key Info : https://docs.kraken.com/api/docs/rest-api/get-api-key-info
