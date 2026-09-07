# CHANGELOG — Batch 12 — Dashboard V1

**Date :** 2026-09-07  
**Baseline Git :** `8f6e3be28b2d987072897e5d90744f458cf40b4a`  
**Baseline tests :** 264  
**Tests Batch 12 :** 48  
**Total attendu :** 312

## Ajouté

### Read models Dashboard

- modèles Pydantic figés pour l'état global, comptes PAPER, positions, ordres,
  fills, opportunités, décisions, propositions, risque, coûts IA, métriques Batch 10,
  comparaison Batch 11, contrefactuels et événements ;
- provenance explicite `SHADOW_PAPER`, `PAPER_EXECUTED`, `COUNTERFACTUAL`,
  `UNAVAILABLE` ;
- disponibilité explicite `AVAILABLE`, `PARTIAL`, `UNAVAILABLE`, `UNBOUNDED` ;
- état initial seedé avec les trois identités Batch 11 mais aucune valeur runtime inventée.

### Projection PAPER/SHADOW

- `ShadowDashboardProjector` lit les résultats Batch 11 et les méthodes publiques
  `get_account_state`, `get_positions`, `get_orders`, `get_fills` du Paper Broker ;
- séparation Professor / proposition / Risk Engine ;
- reason codes risque conservés ;
- coûts IA scindés par système, agent et modèle ;
- métriques Batch 10 conservées avec leur disponibilité ;
- contrefactuels explicitement marqués comme simulations ;
- comparaison Batch 11 projetée sans winner, promotion ni modification du risque ;
- événements audit, risque, sécurité et évaluation projetés.

### Store d'observabilité

- `DashboardStore` en mémoire, thread-safe et borné ;
- historique récent des opportunités, décisions et événements ;
- rejet backend de toute projection LIVE/non-SHADOW/non-PAPER ;
- aucune méthode de trading, promotion ou modification du risque.

### Observateur non autoritaire

- `DashboardShadowObserver` décore un runner Batch 11 ;
- publication du snapshot uniquement après retour du runner ;
- une panne Dashboard ne modifie jamais le résultat SHADOW/PAPER.

### API et interface

- routes GET-only sous `/api/dashboard/*` ;
- page `/dashboard` et assets statiques sans nouvelle dépendance ;
- affichage responsive des trois systèmes, capital/cash/equity PAPER, positions,
  ordres/fills, opportunités, décisions, coûts IA, Batch 10, comparaison et audit ;
- labels explicites PAPER, SHADOW, READ-ONLY, LIVE DÉSACTIVÉ et COUNTERFACTUAL ;
- rendu `Indisponible` lorsque la donnée n'existe pas.

## Modifié

- `app/api/router.py` inclut le routeur Dashboard en plus du routeur health existant.

## Non modifié intentionnellement

- Risk Engine et ses règles ;
- profils de risque ;
- Paper Broker ;
- orchestration IA ;
- logique SHADOW Batch 11 ;
- Evaluation Batch 10 ;
- configuration des limites constitutionnelles.

## Hors périmètre maintenu

- LIVE / Live Broker / exchange réel ;
- promotion automatique ;
- changement automatique du risque ;
- utilisation du SelfFundingRatio par le Risk Engine ;
- Rio / Denver ;
- Recruitment Engine ;
- réputation multidimensionnelle complète ;
- tests d'ablation complets.

## Dépendances / migrations / secrets

- nouvelles dépendances : aucune ;
- migrations : aucune ;
- nouvelles variables d'environnement : aucune ;
- secrets : aucun.
