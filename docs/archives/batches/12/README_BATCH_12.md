# Money Heist — Batch 12 — Dashboard V1

## Objectif

Le Batch 12 ajoute une première couche d'observabilité **read-only** au-dessus des
Batchs 09, 10 et 11, sans créer de nouvelle autorité métier.

Le flux visé reste :

```text
état existant
→ projection/read models
→ API GET-only
→ Dashboard V1
→ observabilité PAPER/SHADOW
```

## Périmètre livré

- Dashboard web V1 sans framework frontend supplémentaire ;
- trois identités SHADOW Batch 11 avec `system_id`, famille, alias et mode ;
- capital initial PAPER, cash, equity, PnL, frais et exposition lorsque disponibles ;
- positions ouvertes, ordres et fills PAPER via les méthodes de lecture publiques du Paper Broker ;
- opportunités scanner récentes, sans leur inventer de direction de trade ;
- historique borné des décisions par système ;
- statuts `NO_ANALYSIS`, `NO_TRADE`, `RISK_REJECTED`, `EXECUTED`,
  `DUPLICATE_BLOCKED`, `FAILED` et autres statuts existants projetés tels quels ;
- décision finale du Professor et `TradeProposal` clairement séparées de l'autorisation risque ;
- décision du Risk Engine avec `reason_codes` ;
- coûts IA par système, agent et modèle lorsque les données existent ;
- métriques Batch 10, dont Trading Net, Economic Net, drawdown et SelfFundingRatio ;
- résultats contrefactuels explicitement marqués `COUNTERFACTUAL` ;
- comparaison Batch 11 avec `AVAILABLE / PARTIAL / UNAVAILABLE` ;
- événements d'audit, risque, évaluation et sécurité pertinents ;
- valeurs absentes conservées comme indisponibles, jamais remplacées par zéro ;
- observateur optionnel `DashboardShadowObserver` qui publie après un run SHADOW
  sans pouvoir modifier le résultat métier.

## Frontières d'autorité

Le Dashboard V1 :

- n'expose aucun endpoint HTTP d'écriture ;
- n'appelle jamais le Risk Engine ;
- n'appelle jamais l'orchestration pour provoquer une décision ;
- n'appelle aucune méthode mutante du Paper Broker ;
- n'expose aucun Live Broker ;
- ne crée aucun ordre LIVE ;
- ne promeut aucun système ;
- ne modifie aucun profil de risque ;
- n'utilise pas le SelfFundingRatio comme entrée de risque ;
- n'ajoute ni Recruitment Engine, ni Rio, ni Denver.

Le `DashboardStore` refuse en plus toute projection déclarant une exécution LIVE,
un système non-SHADOW ou un mode d'exécution autre que PAPER.

## Dépendances

Aucune nouvelle dépendance Python ou frontend.

Le Dashboard utilise uniquement les dépendances déjà présentes, notamment FastAPI
et Pydantic, avec HTML/CSS/JavaScript statiques.

## API de lecture

```text
GET  /dashboard
HEAD /dashboard
GET  /dashboard/assets/dashboard.css
GET  /dashboard/assets/dashboard.js

GET  /api/dashboard/overview
GET  /api/dashboard/systems
GET  /api/dashboard/systems/{system_id}
GET  /api/dashboard/opportunities
GET  /api/dashboard/decisions
GET  /api/dashboard/comparison
GET  /api/dashboard/events?limit=100
```

Aucune route POST/PUT/PATCH/DELETE n'est ajoutée par le Batch 12.

## État initial

Tant qu'aucun `ShadowFleetResult` n'a été observé dans le processus courant, le
Dashboard affiche les trois systèmes Batch 11 mais leurs données runtime restent
explicitement `UNAVAILABLE`. Il ne fabrique ni cash, ni equity, ni PnL, ni coût IA.

## Tests

Baseline attendue : **264 tests**.

Nouveaux tests Batch 12 : **48**.

Total attendu après intégration : **312 tests**.
