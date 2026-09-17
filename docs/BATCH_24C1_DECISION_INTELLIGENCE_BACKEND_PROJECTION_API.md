# Money Heist — Batch 24C.1 — Decision Intelligence Backend Projection API

**Baseline auditée :** `6d915dbff16991cb165d05bc58ab9826b2340c43`  
**Commit :** `feat(evaluation): add funnel stage analytics attribution`  
**Statut :** 24C.1 — implémentation de projection frontend  
**Autorité :** read-only, projection-only, déterministe, zéro autorité de trading

## 1. Objectif

24C.1 expose au Frontend V2 les artefacts déjà calculés par 24A et 24B sans relancer le
Historical Replay, le Scanner, les agents, le Risk Engine ou Analytics.

Le sens de dépendance reste :

```text
artefacts 24A / 24B pré-calculés
        ↓
FrontendDecisionIntelligenceProjectionService
        ↓
FastAPI /api/frontend/v2
        ↓
Zod + TanStack Query
```

La couche de projection n'est jamais une nouvelle source de vérité.

## 2. Audit de la baseline

La baseline contient :

- 24A : `AnalyticsLabRun`, `AnalyticsLabManifest`, `AnalyticsSnapshot`, indicateurs, événements,
  structure, ZigZag causal, patterns, calibration, contexts et sequences ;
- 24B.1 : `OpportunityAnalyticsLinkSet` et matching exact same-as-of ;
- 24B.2 : `DecisionIntelligenceRecordSet` ;
- 24B.3 : `ScannerAnalyticsAttributionSet`, incluant toutes les évaluations Scanner ;
- 24B.4 : `FunnelStageAnalyticsAttributionSet`, avec `market_as_of` séparé de
  `operational_at` ;
- Frontend V2 : Next.js / React / TypeScript / Zod / TanStack Query / Lightweight Charts ;
- Replay V2 : `GET /api/frontend/v2/backtests/runs/{campaign_id}/replay`.

Le Replay V2 reste inchangé.

### Limite d'intégration constatée

Le sidecar `FrontendV2Store` persiste les inputs de campagne, progression, traces, résumé et
exports Batch 16. Il ne calcule ni ne persiste automatiquement les artefacts 24A/24B.

24C.1 ne contourne pas cette frontière. Les endpoints lisent uniquement un bundle frontend
pré-calculé et persisté sous :

```text
frontend-decision-intelligence-design.json
frontend-decision-intelligence-validation.json
frontend-decision-intelligence-oos.json
```

Un run historique qui ne possède pas ce bundle reste consultable via le Replay classique et
retourne explicitement `analytics_available=false` / `decision_intelligence_available=false`.

## 3. Endpoints

```text
GET /api/frontend/v2/backtests/runs/{campaign_id}/analytics?role=OOS
GET /api/frontend/v2/backtests/runs/{campaign_id}/analytics/scanner?role=OOS
GET /api/frontend/v2/backtests/runs/{campaign_id}/opportunities/{opportunity_id}/decision-intelligence?role=OOS
```

`role` accepte `DESIGN`, `VALIDATION` ou `OOS` et vaut `OOS` par défaut.

### Sémantique HTTP

- campagne inconnue : `404` ;
- campagne connue mais bundle 24A/24B absent : `200` avec disponibilité explicite à `false` ;
- bundle disponible mais opportunité inconnue : `404` ;
- opportunité connue par le linking mais Decision Intelligence absent : `200` avec
  `decision_intelligence_available=false` ;
- bundle persisté invalide : `500` explicite, jamais une réponse silencieuse vide.

## 4. Stratégie de payload

### Analytics summary / timeline

Le endpoint `/analytics` retourne :

- identité `BacktestRun` ↔ `AnalyticsLabRun` ;
- dataset/version/SHA/source ;
- rôle de période ;
- source timeframe et decision timeframe ;
- MTF policy ;
- versions de composants ;
- `analytics_sha256` ;
- compteurs ;
- timeline légère des snapshots : id, `as_of`, fingerprint, cursor fingerprint et noms de
  composants.

Il ne retourne pas tous les composants Analytics riches dans chaque snapshot. Cela évite un
mega-payload tout en conservant les identités nécessaires aux futurs overlays.

### Scanner

`/analytics/scanner` retourne une ligne par évaluation Scanner déjà attribuée :

- classification ;
- score / priority score ;
- seuil et marge ;
- triggers ;
- CandidateOpportunity éventuelle ;
- statut du lien Analytics et snapshot same-as-of éventuel.

### Decision Intelligence detail

Le endpoint détail retourne une seule opportunité :

- lien Opportunity ↔ Analytics ;
- record 24B.2 ;
- Scanner causal ;
- DecisionContext ref ;
- décision structurée déjà persistée ;
- stages 24B.4 dans leur ordre canonique.

Aucun Forward Outcome n'est fusionné dans ces objets causaux.

## 5. Causalité

24C.1 préserve les contrats 24A/24B :

```text
market_as_of != operational_at
```

`market_as_of` reste l'instant causal utilisé pour l'attribution Analytics. `operational_at`
reste un diagnostic facultatif pour les étapes qui possèdent un timestamp fiable.

Les timestamps des composants Analytics riches (par exemple `pivot_at` / `confirmed_at` ou
`event_at` / `available_at`) restent dans les artefacts 24A canoniques ; ils ne sont pas aplatis
ni réinterprétés par 24C.1.

## 6. Précision et sérialisation

Les projections Pydantic restent strictes (`extra="forbid"`) et les datetimes sont normalisés en
UTC. Les `Decimal` provenant du record décisionnel sont sérialisés en chaînes lorsqu'ils sont
projetés dans le document JSON générique de décision afin d'éviter une conversion flottante
arbitraire.

Les collections de records conservent l'ordre canonique 24B. Le bundle frontend refuse une
liste de décisions ou de funnel stages non triée.

## 7. Frontend

Les nouveaux contrats sont validés côté navigateur avec Zod. Les fonctions API ajoutées sont :

```text
analyticsQuery(...)
scannerAnalyticsQuery(...)
decisionIntelligenceQuery(...)
```

Les hooks préparatoires sont :

```text
useAnalyticsRun(...)
useScannerAnalytics(...)
useDecisionIntelligence(...)
```

24C.1 n'ajoute aucun overlay graphique, Inspector complet ou filtre métier.

## 8. Préparation de 24C.2

24C.2 peut consommer les identités stables :

```text
analytics_run_id
snapshot_id
snapshot_fingerprint
source_cursor_fingerprint
observed_at / market_as_of
opportunity_id
```

Les géométries et timestamps causaux détaillés restent propriété des artefacts Analytics 24A ;
une future projection overlays pourra les exposer sans modifier les identités ci-dessus.

## 9. Préparation de 24C.3

24C.3 peut construire un Inspector à partir du endpoint détail avec les sections :

```text
Scanner
Compute Gate
PLAN
Specialists
Palermo
FINAL
TradeProposal
Risk
PAPER
Analytics ref
```

Le texte des agents est projeté tel qu'il a été persisté. Aucun appel IA de résumé,
traduction ou reformulation n'est effectué.

## 10. Sécurité et isolation

Les nouvelles routes sont exclusivement `GET`.

Un guard de tests interdit dans la couche de projection les dépendances de recomputation
connues : Historical Replay runner, Scanner, Risk Engine, pipeline PAPER et builders 24A/24B.

Aucune route 24C.1 ne peut armer le LIVE, modifier un seuil Scanner/Risk, soumettre un ordre ou
accéder à un secret fournisseur/exchange.

## 11. Volumétrie

L'unité la plus volumineuse en 24C.1 est la timeline légère des snapshots, soit environ une ligne
par point Analytics. Le détail riche est volontairement par opportunité, et le Scanner est servi
par un endpoint séparé. Les composants Analytics riches ne sont pas dupliqués dans le résumé.

Cette séparation évite de retourner dans une seule réponse : indicateurs + événements + pivots +
patterns + contexts + sequences + toutes les décisions.

## 12. Roadmap

```text
24A — Analytics Core                         DONE
24B — Decision ↔ Analytics Attribution      DONE
24C.1 — Backend Projection API              CURRENT
24C.2 — Trading Chart Analytics Overlays    NEXT
24C.3 — Decision Intelligence Inspector
24C.4 — Filters & Navigation
```

## 13. Hors scope

24C.1 ne réalise pas :

- le calcul/persistance automatique des artefacts 24A/24B pendant une campagne Frontend V2 ;
- les overlays du chart ;
- l'Inspector complet ;
- les filtres/navigation avancés ;
- les Forward Outcomes dans le payload causal ;
- toute modification Scanner/agents/Risk/PAPER/LIVE.
