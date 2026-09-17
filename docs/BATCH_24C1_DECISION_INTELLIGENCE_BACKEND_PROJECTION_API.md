# Money Heist â€” Batch 24C.1 â€” Decision Intelligence Backend Projection API

**Baseline auditÃ©e :** `6d915dbff16991cb165d05bc58ab9826b2340c43`
**Commit :** `feat(evaluation): add funnel stage analytics attribution`
**Statut :** 24C.1 â€” implÃ©mentation de projection frontend
**AutoritÃ© :** read-only, projection-only, dÃ©terministe, zÃ©ro autoritÃ© de trading

## 1. Objectif

24C.1 expose au Frontend V2 les artefacts dÃ©jÃ  calculÃ©s par 24A et 24B sans relancer le
Historical Replay, le Scanner, les agents, le Risk Engine ou Analytics.

Le sens de dÃ©pendance reste :

```text
artefacts 24A / 24B prÃ©-calculÃ©s
        â†“
FrontendDecisionIntelligenceProjectionService
        â†“
FastAPI /api/frontend/v2
        â†“
Zod + TanStack Query
```

La couche de projection n'est jamais une nouvelle source de vÃ©ritÃ©.

## 2. Audit de la baseline

La baseline contient :

- 24A : `AnalyticsLabRun`, `AnalyticsLabManifest`, `AnalyticsSnapshot`, indicateurs, Ã©vÃ©nements,
  structure, ZigZag causal, patterns, calibration, contexts et sequences ;
- 24B.1 : `OpportunityAnalyticsLinkSet` et matching exact same-as-of ;
- 24B.2 : `DecisionIntelligenceRecordSet` ;
- 24B.3 : `ScannerAnalyticsAttributionSet`, incluant toutes les Ã©valuations Scanner ;
- 24B.4 : `FunnelStageAnalyticsAttributionSet`, avec `market_as_of` sÃ©parÃ© de
  `operational_at` ;
- Frontend V2 : Next.js / React / TypeScript / Zod / TanStack Query / Lightweight Charts ;
- Replay V2 : `GET /api/frontend/v2/backtests/runs/{campaign_id}/replay`.

Le Replay V2 reste inchangÃ©.

### Limite d'intÃ©gration constatÃ©e

Le sidecar `FrontendV2Store` persiste les inputs de campagne, progression, traces, rÃ©sumÃ© et
exports Batch 16. Il ne calcule ni ne persiste automatiquement les artefacts 24A/24B.

24C.1 ne contourne pas cette frontiÃ¨re. Les endpoints lisent uniquement un bundle frontend
prÃ©-calculÃ© et persistÃ© sous :

```text
frontend-decision-intelligence-design.json
frontend-decision-intelligence-validation.json
frontend-decision-intelligence-oos.json
```

Un run historique qui ne possÃ¨de pas ce bundle reste consultable via le Replay classique et
retourne explicitement `analytics_available=false` / `decision_intelligence_available=false`.

## 3. Endpoints

```text
GET /api/frontend/v2/backtests/runs/{campaign_id}/analytics?role=OOS
GET /api/frontend/v2/backtests/runs/{campaign_id}/analytics/scanner?role=OOS
GET /api/frontend/v2/backtests/runs/{campaign_id}/opportunities/{opportunity_id}/decision-intelligence?role=OOS
```

`role` accepte `DESIGN`, `VALIDATION` ou `OOS` et vaut `OOS` par dÃ©faut.

### SÃ©mantique HTTP

- campagne inconnue : `404` ;
- campagne connue mais bundle 24A/24B absent : `200` avec disponibilitÃ© explicite Ã  `false` ;
- bundle disponible mais opportunitÃ© inconnue : `404` ;
- opportunitÃ© connue par le linking mais Decision Intelligence absent : `200` avec
  `decision_intelligence_available=false` ;
- bundle persistÃ© invalide : `500` explicite, jamais une rÃ©ponse silencieuse vide.

## 4. StratÃ©gie de payload

### Analytics summary / timeline

Le endpoint `/analytics` retourne :

- identitÃ© `BacktestRun` â†” `AnalyticsLabRun` ;
- dataset/version/SHA/source ;
- rÃ´le de pÃ©riode ;
- source timeframe et decision timeframe ;
- MTF policy ;
- versions de composants ;
- `analytics_sha256` ;
- compteurs ;
- timeline lÃ©gÃ¨re des snapshots : id, `as_of`, fingerprint, cursor fingerprint et noms de
  composants.

Il ne retourne pas tous les composants Analytics riches dans chaque snapshot. Cela Ã©vite un
mega-payload tout en conservant les identitÃ©s nÃ©cessaires aux futurs overlays.

### Scanner

`/analytics/scanner` retourne une ligne par Ã©valuation Scanner dÃ©jÃ  attribuÃ©e :

- classification ;
- score / priority score ;
- seuil et marge ;
- triggers ;
- CandidateOpportunity Ã©ventuelle ;
- statut du lien Analytics et snapshot same-as-of Ã©ventuel.

### Decision Intelligence detail

Le endpoint dÃ©tail retourne une seule opportunitÃ© :

- lien Opportunity â†” Analytics ;
- record 24B.2 ;
- Scanner causal ;
- DecisionContext ref ;
- dÃ©cision structurÃ©e dÃ©jÃ  persistÃ©e ;
- stages 24B.4 dans leur ordre canonique.

Aucun Forward Outcome n'est fusionnÃ© dans ces objets causaux.

## 5. CausalitÃ©

24C.1 prÃ©serve les contrats 24A/24B :

```text
market_as_of != operational_at
```

`market_as_of` reste l'instant causal utilisÃ© pour l'attribution Analytics. `operational_at`
reste un diagnostic facultatif pour les Ã©tapes qui possÃ¨dent un timestamp fiable.

Les timestamps des composants Analytics riches (par exemple `pivot_at` / `confirmed_at` ou
`event_at` / `available_at`) restent dans les artefacts 24A canoniques ; ils ne sont pas aplatis
ni rÃ©interprÃ©tÃ©s par 24C.1.

## 6. PrÃ©cision et sÃ©rialisation

Les projections Pydantic restent strictes (`extra="forbid"`) et les datetimes sont normalisÃ©s en
UTC. Les `Decimal` provenant du record dÃ©cisionnel sont sÃ©rialisÃ©s en chaÃ®nes lorsqu'ils sont
projetÃ©s dans le document JSON gÃ©nÃ©rique de dÃ©cision afin d'Ã©viter une conversion flottante
arbitraire.

Les collections de records conservent l'ordre canonique 24B. Le bundle frontend refuse une
liste de dÃ©cisions ou de funnel stages non triÃ©e.

## 7. Frontend

Les nouveaux contrats sont validÃ©s cÃ´tÃ© navigateur avec Zod. Les fonctions API ajoutÃ©es sont :

```text
analyticsQuery(...)
scannerAnalyticsQuery(...)
decisionIntelligenceQuery(...)
```

Les hooks prÃ©paratoires sont :

```text
useAnalyticsRun(...)
useScannerAnalytics(...)
useDecisionIntelligence(...)
```

24C.1 n'ajoute aucun overlay graphique, Inspector complet ou filtre mÃ©tier.

## 8. PrÃ©paration de 24C.2

24C.2 peut consommer les identitÃ©s stables :

```text
analytics_run_id
snapshot_id
snapshot_fingerprint
source_cursor_fingerprint
observed_at / market_as_of
opportunity_id
```

Les gÃ©omÃ©tries et timestamps causaux dÃ©taillÃ©s restent propriÃ©tÃ© des artefacts Analytics 24A ;
une future projection overlays pourra les exposer sans modifier les identitÃ©s ci-dessus.

## 9. PrÃ©paration de 24C.3

24C.3 peut construire un Inspector Ã  partir du endpoint dÃ©tail avec les sections :

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

Le texte des agents est projetÃ© tel qu'il a Ã©tÃ© persistÃ©. Aucun appel IA de rÃ©sumÃ©,
traduction ou reformulation n'est effectuÃ©.

## 10. SÃ©curitÃ© et isolation

Les nouvelles routes sont exclusivement `GET`.

Un guard de tests interdit dans la couche de projection les dÃ©pendances de recomputation
connues : Historical Replay runner, Scanner, Risk Engine, pipeline PAPER et builders 24A/24B.

Aucune route 24C.1 ne peut armer le LIVE, modifier un seuil Scanner/Risk, soumettre un ordre ou
accÃ©der Ã  un secret fournisseur/exchange.

## 11. VolumÃ©trie

L'unitÃ© la plus volumineuse en 24C.1 est la timeline lÃ©gÃ¨re des snapshots, soit environ une ligne
par point Analytics. Le dÃ©tail riche est volontairement par opportunitÃ©, et le Scanner est servi
par un endpoint sÃ©parÃ©. Les composants Analytics riches ne sont pas dupliquÃ©s dans le rÃ©sumÃ©.

Cette sÃ©paration Ã©vite de retourner dans une seule rÃ©ponse : indicateurs + Ã©vÃ©nements + pivots +
patterns + contexts + sequences + toutes les dÃ©cisions.

## 12. Roadmap

```text
24A â€” Analytics Core                         DONE
24B â€” Decision â†” Analytics Attribution      DONE
24C.1 â€” Backend Projection API              CURRENT
24C.2 â€” Trading Chart Analytics Overlays    NEXT
24C.3 â€” Decision Intelligence Inspector
24C.4 â€” Filters & Navigation
```

## 13. Hors scope

24C.1 ne rÃ©alise pas :

- le calcul/persistance automatique des artefacts 24A/24B pendant une campagne Frontend V2 ;
- les overlays du chart ;
- l'Inspector complet ;
- les filtres/navigation avancÃ©s ;
- les Forward Outcomes dans le payload causal ;
- toute modification Scanner/agents/Risk/PAPER/LIVE.

