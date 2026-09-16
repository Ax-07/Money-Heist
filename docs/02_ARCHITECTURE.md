# Money Heist — Architecture Technique

**Document :** Architecture technique  
**Version :** 0.4
**Statut :** Architecture active — alignée post-Batch 23A.4
**Référence :** `01_PROJECT_MASTER.md`

---

## 1. Objectif

Ce document décrit l’architecture logique de Money Heist : composants, responsabilités, frontières de sécurité, flux de données, modes d’exécution et dépendances.

Il ne fige pas encore les décisions explicitement laissées ouvertes dans le document maître, notamment :
- exchange initial ;
- spot ou dérivés ;
- timeframes exacts ;
- limites numériques du profil Balanced ;
- base de données finale ;
- environnement de déploiement.

L’architecture doit permettre de prendre ces décisions sans réécriture majeure.

---

## 2. Principes d’architecture

Money Heist suit six règles structurantes :

1. **Séparation analyse / autorisation / exécution.**
2. **Aucune décision IA ne déclenche directement un ordre réel.**
3. **Les fonctions critiques sont déterministes et testables.**
4. **PAPER, SHADOW et LIVE partagent autant que possible le même pipeline.**
5. **Chaque décision est traçable et reproductible.**
6. **Les composants IA sont remplaçables sans modifier le cœur du trading.**

---

## 3. Vue d’ensemble

```text
                       ┌────────────────────────┐
                       │      MARKET DATA       │
                       │ OHLCV / trades / etc.  │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │ NORMALISATION / CACHE  │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │ SCANNER DÉTERMINISTE   │
                       └───────────┬────────────┘
                                   │ CandidateOpportunity
                                   ▼
                       ┌────────────────────────┐
                       │ AI COMPUTE GATE        │
                       │ budget + priorité      │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │     THE PROFESSOR      │
                       │ orchestration          │
                       └───────────┬────────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
             Berlin              Tokyo             Nairobi
                │                  │                  │
                └──────────────┬───┴───────┬─────────┘
                               ▼           ▼
                              Rio        Denver
                               └──────┬────┘
                                      ▼
                                  Palermo
                                      │
                                      ▼
                              The Professor
                                      │ TradeProposal
                                      ▼
                       ┌────────────────────────┐
                       │ RISK ENGINE            │
                       │ déterministe           │
                       └───────────┬────────────┘
                                   │ AuthorizedTrade
                                   ▼
                       ┌────────────────────────┐
                       │ EXECUTION ROUTER       │
                       └───────┬────────┬───────┘
                               │        │
                           PAPER     LIVE
                               │        │
                               └───┬────┘
                                   ▼
                       ┌────────────────────────┐
                       │ JOURNAL / EVALUATION   │
                       └───────────┬────────────┘
                                   ▼
                               Lisbon
```

---

## 4. Couches principales

### 4.1 Configuration

Responsabilités :
- charger la configuration non sensible ;
- charger les références vers les secrets sans les exposer aux agents ;
- définir le mode `PAPER`, `SHADOW` ou `LIVE` ;
- définir l’univers de marché ;
- définir les profils de risque ;
- définir les budgets IA ;
- définir le routage de modèles.

Contraintes :
- configuration typée ;
- validation au démarrage ;
- échec explicite si une valeur critique manque ;
- aucune valeur secrète dans les logs.

---

### 4.2 Market Data

Responsabilités :
- collecter les données brutes ;
- valider leur fraîcheur ;
- normaliser les formats ;
- détecter les trous de données ;
- produire des snapshots cohérents ;
- exposer des données stables aux calculs.

Le reste du système ne doit pas dépendre directement du format spécifique d’un exchange.

Interface conceptuelle :

```python
class MarketDataProvider:
    async def get_snapshot(self, symbol: str) -> MarketSnapshot: ...
    async def get_candles(self, symbol: str, timeframe: str, limit: int): ...
```

---

### 4.3 Feature Engine

Responsabilités :
- calcul des indicateurs ;
- structure de marché ;
- métriques de volatilité ;
- métriques de volume ;
- variables quantitatives ;
- construction d’un snapshot compact pour les agents.

L’objectif est de **ne pas envoyer des séries brutes massives aux LLM** lorsque des features déterministes suffisent.

---

### 4.4 Scanner

Le scanner fonctionne sans modèle IA dans sa forme de base.

Il produit une `CandidateOpportunity` lorsqu’un événement mérite une inspection.

Exemples de familles de triggers :
- breakout ;
- changement de régime ;
- expansion inhabituelle de volatilité ;
- volume anormal ;
- variation d’open interest ;
- divergence ;
- proximité d’une zone importante.

Le scanner ne décide jamais `LONG` ou `SHORT` à lui seul.

---

### 4.5 AI Compute Gate

Ce composant protège le budget IA.

Entrées :
- opportunité ;
- priorité ;
- budget restant ;
- coût estimé ;
- niveau d’analyse requis.

Sorties :
- `SKIP_AI` ;
- `LEVEL_1_SENTINEL` ;
- `LEVEL_2_MINI_CREW` ;
- `LEVEL_3_FULL_CREW`.

Les limites dures sont appliquées par code.

---

### 4.6 Orchestrateur Money Heist

The Professor orchestre les spécialistes via une interface commune.

Responsabilités :
- décider quels spécialistes appeler ;
- garantir le minimum de contradiction requis ;
- préserver l’indépendance du premier tour ;
- compiler les analyses ;
- décider si un second tour vaut son coût ;
- produire une proposition finale structurée.

L’orchestrateur ne reçoit pas les clés exchange et n’appelle jamais directement le connecteur d’exécution LIVE.

---

### 4.7 Risk Engine

Composant déterministe.

Entrée :

```text
TradeProposal
+
PortfolioState
+
RiskProfile
+
MarketConstraints
```

Sortie :

```text
APPROVED
REJECTED
RESIZED
```

Toute modification d’une proposition doit être explicitement journalisée.

---

### 4.8 Execution Router

Route une décision autorisée vers :
- `PaperBroker` ;
- `LiveBroker`.

Le mode est défini par la configuration du système et ne peut pas être changé par un agent.

---

### 4.9 Storage / Journal

Stockage de :
- market snapshots utilisés ;
- opportunités ;
- exécutions d’agents ;
- coûts IA ;
- propositions ;
- décisions Risk Engine ;
- ordres ;
- fills ;
- positions ;
- résultats ;
- événements de sécurité ;
- changements de configuration.

Chaque objet majeur possède un identifiant stable.

---

### 4.10 Evaluation

Responsabilités :
- calcul des performances ;
- calibration des agents ;
- attribution marginale ;
- comparaison des crews ;
- évaluation des profils SHADOW ;
- préparation des données pour Lisbon.

Aucune métrique d’évaluation ne doit modifier immédiatement les règles LIVE sans processus contrôlé.

---

## 5. Modèle événementiel

Le prototype peut commencer comme une application monolithique modulaire, tout en utilisant un modèle d’événements interne.

Événements conceptuels :

```text
MarketSnapshotCreated
CandidateOpportunityCreated
AIAnalysisRequested
AgentAnalysisCompleted
TradeProposalCreated
RiskDecisionCreated
OrderSubmitted
OrderFilled
PositionOpened
PositionClosed
AICostRecorded
SafetyLimitTriggered
```

Objectif :
- découpler les composants ;
- faciliter les tests ;
- reconstruire une décision ;
- permettre une migration future vers une architecture distribuée si nécessaire.

---

## 6. Pipeline runtime

### 6.1 Surveillance

```text
1. Réception des données
2. Validation
3. Normalisation
4. Calcul des features
5. Scanner
6. Création éventuelle d’une opportunité
```

### 6.2 Analyse IA

```text
1. Compute Gate
2. Professor : plan d’analyse
3. Spécialistes en parallèle
4. Agrégation
5. Palermo
6. Professor : proposition finale
```

### 6.3 Autorisation et exécution

```text
1. Validation du schéma
2. Risk Engine
3. Rejet ou autorisation
4. Execution Router
5. Paper/Live Broker
6. Réconciliation
7. Journalisation
```

### 6.4 Evaluation

```text
1. Mise à jour position
2. Calcul du résultat
3. Attribution
4. Calcul des coûts
5. Mise à jour des métriques agent
6. Rapport Lisbon
```

---

## 7. PAPER, SHADOW et LIVE

### PAPER

Simulation complète avec capital virtuel.

Aucun appel d’ordre réel.

### SHADOW

Le système peut fonctionner en parallèle d’un système LIVE.

Il :
- observe les mêmes marchés ;
- prend ses propres décisions ;
- simule ses trades ;
- n’influence pas le système LIVE.

### LIVE

Les décisions autorisées peuvent être envoyées à l’exchange.

Conditions minimales avant activation :
- Risk Engine validé ;
- kill switch fonctionnel ;
- tests de réconciliation ;
- API sans droit de retrait ;
- plafond de risque configuré ;
- logs persistants ;
- comportement fail-safe vérifié.

---

## 8. Isolation des systèmes

Chaque profil ou crew doit avoir :
- son `system_id` ;
- son portefeuille logique ;
- sa configuration ;
- son budget IA ;
- ses métriques ;
- son état LIVE/SHADOW.

Les données de marché peuvent être partagées.

Les décisions, budgets et expositions ne doivent pas être implicitement partagés.

---

## 9. Frontières de panne

### Données invalides
Action : bloquer toute nouvelle position utilisant ces données.

### API IA indisponible
Action : pas de nouvelle proposition IA ; gestion déterministe des positions déjà ouvertes.

### Sortie IA invalide
Action : rejet de l’analyse ; possibilité d’un retry borné.

### Base de données indisponible
Action : par défaut, bloquer les nouvelles positions si l’audit ne peut pas être garanti.

### Exchange indisponible
Action : ne pas ouvrir de nouvelles positions ; tenter uniquement les actions de sécurité autorisées selon le contexte.

### Budget IA épuisé
Action : aucune dépense supplémentaire ; bascule possible vers analyse déterministe ou arrêt des nouvelles analyses IA.

---

## 10. Concurrence et idempotence

Le système doit éviter :
- double exécution ;
- double traitement d’une opportunité ;
- répétition d’un ordre après timeout ;
- deux décisions concurrentes sur la même position sans arbitrage.

Concepts requis :
- `event_id` ;
- `opportunity_id` ;
- `proposal_id` ;
- `client_order_id` ;
- verrou logique par système/symbole si nécessaire ;
- opérations idempotentes.

---

## 11. Déploiement V1

La V1 doit privilégier la simplicité :

```text
Une application backend
+
Une base de données
+
Un scheduler / loop de marché
+
Un dashboard web
```

Une architecture microservices n’est pas nécessaire au départ.

Le code doit cependant conserver des frontières de modules suffisamment nettes pour permettre une extraction future.

---

## 12. Observabilité

Minimum :
- logs structurés ;
- niveaux INFO/WARNING/ERROR/CRITICAL ;
- identifiants de corrélation ;
- métriques de latence ;
- coût IA ;
- erreurs API ;
- état des connexions ;
- alertes sécurité ;
- nombre d’opportunités ;
- nombre de propositions ;
- nombre de rejets.

---

## 13. Dépendances autorisées entre couches

Règle générale :

```text
api
 ↓
services/orchestration
 ↓
domain
 ↓
ports/interfaces

infrastructure
 ↑ implémente les ports
```

Éviter que :
- les agents importent directement l’exchange ;
- le Risk Engine dépende du SDK IA ;
- la logique métier dépende du framework FastAPI ;
- la base de données dicte les objets métier.

---

## 14. Décisions à prendre avant Batch 01

Batch 01 ne nécessite pas encore le choix de l’exchange.

Il faut toutefois figer :
- version Python cible ;
- gestionnaire de dépendances ;
- style de configuration ;
- type de base locale initiale ;
- framework de tests.

Ces décisions seront consignées dans `10_DECISIONS_ET_CHANGELOG.md`.

---

## 15. Critères d’acceptation de l’architecture

L’architecture est considérée correctement appliquée si :
- un agent ne peut pas exécuter directement un trade ;
- PAPER et LIVE utilisent les mêmes objets métier ;
- le Risk Engine est indépendant des LLM ;
- chaque appel IA est comptabilisé ;
- chaque proposition est liée au snapshot utilisé ;
- chaque ordre est lié à une décision autorisée ;
- une panne critique bloque les nouvelles positions ;
- un nouveau spécialiste peut être ajouté sans modifier le Risk Engine.


---

## 16. Addendum Batch 16 — frontière Backtest / Historical Replay

Le package `app/services/backtest` est une couche de service historique distincte de l’exécution LIVE.

Flux :

```text
HistoricalReplayRunner
→ FeatureEngine
→ DeterministicScanner
→ PaperTradingPipeline
→ RiskEngine
→ PaperBroker
```

Le runner contrôle uniquement la chronologie et l’adaptation historique. Il ne réimplémente pas les décisions des agents, le Risk Engine ni la logique d’ordre PAPER.

Les dépendances LIVE sont interdites depuis le package backtest. `LIVE_EVAL` ne concerne que le choix du client IA du Batch 06 ; le broker reste PAPER.

Les composants Batch 16 principaux sont :
- `DatasetRef` ;
- `ReplayClock` / `ReplayIdFactory` ;
- `HistoricalReplayRunner` ;
- `BacktestPortfolioStateProvider` ;
- `HistoricalPositionLifecycle` ;
- résolution intrabar STOP_FIRST ;
- `BacktestAIClient` et cache ;
- adaptateur Evaluation ;
- fingerprint business ;
- splits DESIGN/VALIDATION/OOS ;
- walk-forward V1 ;
- exports déterministes.

---

## 17. Addendum Batch 16.7 — frontière Dashboard / Backtest

L'API expose une couche opérateur distincte :

```text
Browser /dashboard/backtest
→ FastAPI backtest-dashboard
→ BacktestDashboardService
→ Batch 16 Historical Replay
→ PaperTradingPipeline / RiskEngine / PaperBroker
```

`BacktestDashboardService` orchestre les composants existants mais ne possède aucune dépendance vers `app.trading.live`. Les secrets fournisseurs ne transitent ni dans les modèles métier ni dans le navigateur.


---

## 18. Addendum Batch 19 — frontière Recruitment

`app/recruitment` constitue une couche de domaine/service séparée du registre opérationnel des agents et de l'exécution LIVE.

```text
RecruitmentProposal
→ RecruitmentCandidateSpec gelé
→ Recruitment lifecycle séparé
→ Candidate campaign plan
→ HistoricalReplayRunner / PAPER
→ comparability + provenance + OOS gates
→ Batch 18 ablation / reputation
→ CandidateEvidencePackage
→ RecruitmentAdvisory
→ operator-gated transition plan
→ audit FRESH / STALE
```

Règles de dépendance :
- un candidat Recruitment n'est pas inscrit automatiquement dans `AgentRegistry` ;
- Recruitment ne modifie pas le `RiskEngine` ;
- les campagnes candidates réutilisent Batch 16 et le broker PAPER, sans second moteur de replay ;
- baseline et candidat utilisent des runners/brokers isolés ;
- les seuils de capacité/budget sont injectés par politique opérateur, pas codés comme seuils magiques ;
- les critères de succès sont pré-enregistrés et exigent une preuve OOS pour l'advisory de promotion ;
- `PROMOTION_RECOMMENDED` reste un état Recruitment, pas un `AgentState.ACTIVE` ;
- l'API HTTP Recruitment V1 est read-only et n'expose que les capabilities.

Cette frontière conserve le principe architectural : l'IA ou l'évaluation peut proposer/recommander, tandis que les systèmes déterministes et l'opérateur gardent l'autorité.

<!-- BATCH20_ARCHITECTURE_START -->

## Addendum Batch 20 — Architecture Task Force

Le package `app.task_force` est un sibling fonctionnel de Recruitment et non un sous-système de
trading. Il dépend des contrats agents/AI Gateway/evaluation mais ne possède aucune dépendance vers
le broker LIVE ou une API exchange d’ordre.

Architecture logique :

```text
orchestration trigger bridge
→ app.task_force models/lifecycle/gates
→ composition + provenance/stale
→ execution contract/runtime via AI Gateway
→ aggregation
→ orchestration report bridge
```

La composition reste registry-only. Les candidats Batch 19 non inscrits au registre ne sont pas
sélectionnables. Les stale guards entourent composition et replay afin qu’un changement matériel
impose une régénération plutôt qu’une réutilisation silencieuse.

<!-- BATCH20_ARCHITECTURE_END -->

<!-- BATCH22_FRONTEND_V2 -->
## Addendum Batch 22 — Frontend V2 / Trading Cockpit

Le frontend devient une application séparée `frontend/` en Next.js + React + TypeScript. FastAPI reste l'autorité métier. Le navigateur accède aux contrats via un proxy Next server-side et une couche API centralisée/Zod.

Le Frontend V2 ne recalcule ni Feature Engine, ni Scanner, ni TradeProposal, ni RiskDecision, ni backtest. L'extension FastAPI `/api/frontend/v2` expose seulement les capacités non sensibles, les candles Kraken publiques et un adapter de replay autour du moteur Batch 16.

Aucun WebSocket/SSE opérateur n'existant dans la baseline `34351184f193e658a375667bdf19594d2defb3ec`, la V2 utilise un polling centralisé TanStack Query. Toute future couche temps réel devra conserver une connexion centralisée et ne changera pas les frontières de sécurité.

<!-- BATCH22_1_BACKTEST_COCKPIT -->
## Addendum Batch 22.1 — Backtest Cockpit durable

Frontend V2 conserve `BacktestDashboardService` comme autorité d'exécution mais ajoute un sidecar durable sous `.money-heist/frontend-v2/`. Il persiste bibliothèque de datasets, configuration figée, progression/traces, résumé et exports nécessaires au replay. Aucun calcul métier n'est déplacé hors du moteur Batch 16.

<!-- DOC_REALIGN_POST_BATCH22_ARCHITECTURE_START -->

## Alignement architecture post-Batch 22.1 — 2026-09-15

L’architecture est maintenant implémentée au-delà de la spécification initiale. Les éléments suivants font partie de l’état intégré :

```text
FastAPI backend
├─ Market Data / Feature Engine / Scanner
├─ AI Gateway + Prompt Cache OpenAI explicite
├─ Orchestration Professor / spécialistes / Palermo
├─ Risk Engine déterministe
├─ PAPER / SHADOW / LIVE protégés
├─ Historical Replay / Backtest
├─ Recruitment / Task Force
├─ Master Portfolio Layer
└─ API Frontend V2
        ↓
Next.js Frontend V2 / Backtest Cockpit
```

Le Prompt Cache est une optimisation de transport/coût du AI Gateway. Il n’est ni une mémoire métier ni une source d’autorité. Le Master Professor reste advisory/operator-gated. Le Frontend reste un client du backend et ne recalcule aucune décision critique.

<!-- DOC_REALIGN_POST_BATCH22_ARCHITECTURE_END -->

<!-- BATCH23A1_ARCHITECTURE -->
## Addendum Batch 23A.1 — Causal Measurement / Decision Funnel

`app.evaluation.decision_funnel` est une couche de mesure **read-only** placée après les sorties déjà produites par Historical Replay et Evaluation.

```text
HistoricalReplayResult + Evaluation
→ DecisionFunnel aggregation
→ PeriodSummary / exports JSON
```

Règles d'architecture :
- aucun appel supplémentaire au Scanner, aux agents, au Risk Engine ou au broker ;
- aucun changement de prompt, seuil, sizing ou règle d'exécution ;
- aucun `DecisionFunnelReport` n'est injecté dans `DecisionContext` ;
- les résultats postérieurs au choix sont séparés dans `post_hoc` ;
- seuls deux compteurs techniques pré-Scanner sont ajoutés au runner pour expliquer les bougies non évaluées par le Scanner ;
- l'agrégation est compatible avec une extension future PAPER/SHADOW/LIVE mais Batch 23A.1 est branché d'abord sur Historical Replay.

Cette couche augmente l'observabilité sans déplacer l'autorité métier. Le Risk Engine reste l'autorité finale d'autorisation.

<!-- BATCH23A2_4_ARCHITECTURE -->
## Addendum Batch 23A.2–23A.4 — Causal Measurement Stack

La couche de mesure Historical Replay est désormais composée de quatre vues complémentaires :

```text
HistoricalReplayResult + Evaluation
├─ Decision Funnel (23A.1)
├─ Candidate Forward Outcomes (23A.2)
│    └─ Funnel Outcome Attribution (23A.3)
└─ Scanner Forward Outcomes (23A.4)
```

### Forward Outcomes 23A.2

`app.evaluation.forward_outcomes` calcule les mouvements futurs uniquement **après** le replay. Les références proviennent du close du `FeatureSnapshot` au temps de l'observation. Les horizons H1/H3/H5/H10/H20 sont exprimés dans le timeframe de décision.

La couche :
- n'appelle ni Scanner, ni agent, ni Risk Engine, ni broker ;
- ne modifie aucun `DecisionContext` ;
- ne traverse jamais `period_end` d'un split DESIGN / VALIDATION / OOS ;
- ne publie aucune métrique de prix partielle pour un horizon incomplet ;
- distingue gap de données et frontière de période.

### Funnel Outcome Attribution 23A.3

`app.evaluation.funnel_outcome_attribution` croise les Forward Outcomes candidats avec les métadonnées déjà produites par le pipeline : statut terminal, régime, triggers, Compute Gate, Professor PLAN/FINAL, agents sélectionnés, Risk et échecs.

Cette couche est descriptive. Elle n'est ni un optimizer, ni un tuner, ni une autorité de promotion de configuration. Les dimensions multi-valuées restent explicitement non exclusives.

### Scanner Forward Outcomes 23A.4

`app.evaluation.scanner_forward_outcomes` étend la couverture aux évaluations Scanner qui ne deviennent pas `CandidateOpportunity`.

```text
scanner_evaluations
=
NO_TRIGGER
+ TRIGGER_BELOW_CANDIDATE_THRESHOLD
+ CANDIDATE_OPPORTUNITY
```

23A.4 lit le `ScanResult` réellement émis pendant le replay, conserve score exact, seuil candidat réellement utilisé, marge au seuil, triggers et régime, puis réutilise le même moteur de Forward Outcomes que 23A.2. Le Scanner n'est jamais réexécuté pour produire l'analyse post-hoc.

### Frontières communes

Les quatre couches 23A restent hors du chemin d'autorité :

```text
mesure / observation
≠
décision de trading
≠
autorisation Risk
≠
exécution LIVE
```

`BacktestConfig`, `run_id`, prompts, seuils, sizing et fingerprint business historique ne sont pas modifiés par cette pile.

**Références fonctionnelles :** `b78266e` (23A.2), `42903cc` (23A.3), `611bef3` (23A.4).
<!-- BATCH24A1_ARCHITECTURE -->
## Analytics Lab — frontière observation-only (Batch 24A.1)

```text
Historical Replay / DatasetRef / MTF
        ├── Decision pipeline canonique
        └── Analytics Lab (read-only)
                    ↓
              artefacts Analytics
```

`app.analytics` ne possède aucune autorité de trading. Il ne peut ni créer une
opportunité, ni modifier le `DecisionContextV1`, ni influencer
Professor/Palermo/Risk/PAPER/LIVE. Le Lab réutilise l'identité dataset et le
`source_cursor_fingerprint` MTF ; il ne possède pas de seconde source de marché
ni de resampler indépendant.

`BacktestRun != AnalyticsLabRun`. Les versions Analytics restent hors du business
fingerprint tant que la couche demeure observation-only.

<!-- BATCH_24A2_RICH_INDICATORS -->
### Batch 24A.2 — Rich Indicators (observation-only)

`app/analytics/indicators` adds a versioned, deterministic, causal indicator registry beside — not inside — the production Feature Engine. It consumes only canonical closed candles already exposed by Money Heist historical MTF contracts. No decision path imports this package. Analytics indicator identities affect Analytics fingerprints only.

<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Batch 24A.3 — Technical Events

L'Analytics Lab possède désormais une couche `app.analytics.events` strictement
observation-only :

```text
Canonical closed candles
→ Analytics Indicators
→ Technical Events
→ AnalyticsSnapshot / Decision Intelligence future
```

`TechnicalEventEngine` consomme uniquement deux `AnalyticsIndicatorSnapshot` consécutifs.
Il ne recalcule aucun indicateur, ne lit pas le Scanner et ne possède aucune autorité de
trading. Les événements portent `event_at` et `available_at`; pour 24A.3 ils sont égaux au
close/as-of de la snapshot courante. Les chemins Scanner/Decision/Agents/Risk/PAPER/LIVE
restent indépendants et ne doivent pas importer `app.analytics.events`.

<!-- BATCH_24A4_CAUSAL_STRUCTURE_ZIGZAG -->
## Batch 24A.4 — Causal Structure & ZigZag

L'Analytics Lab expose désormais deux sources structurelles distinctes :
la projection read-only du `MarketStructureContextV1` de production et un ZigZag
Analytics causal ATR-confirmé. Le ZigZag ne remplace jamais la structure de production.
`pivot_at` décrit la position géométrique sur une candle close ; `confirmed_at` décrit
le premier instant où le pivot est connaissable. Aucun pivot dont
`confirmed_at > as_of` ne peut entrer dans `AnalyticsSnapshot`.
