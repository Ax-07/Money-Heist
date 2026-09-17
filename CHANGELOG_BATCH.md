# Batch 18a — Réputation et ablation — clôture des fondations

## État

Steps 1 à 4 livrés et conçus comme une couche d’évaluation déterministe/advisory-only.

## Step 1 — Fondations réputation + ablation

- comparaison stricte baseline vs run sans exactement un agent ;
- comparabilité par fingerprint expérimental, dataset, rôle, période, bougies et opportunités ;
- deltas Trading Net / Economic Net / drawdown / coût IA ;
- agrégation d’ablation ;
- `AgentReputationProfile` multidimensionnel ;
- aucune mutation runtime.

## Step 2 — Policy de recommandation d’état

- `AgentStateEvidence` ;
- seuils explicites `ReputationPolicyThresholds` ;
- recommandations `HOLD / PROMOTE / DEMOTE / REDUCE_FREQUENCY` ;
- transitions progressives ;
- fonctions Core protégées ;
- `auto_apply=False`.

## Step 3 — Bridge et rapport auditable

- `ReputationAdvisoryService` ;
- adaptation Step 1 → Step 2 ;
- ablation OOS-only pour la preuve de transition ;
- contrôle du scope de coût IA ;
- provenance runs/datasets/fingerprints ;
- `AgentReputationAdvisoryReport` avec fingerprint SHA-256 déterministe.

## Step 4 — API publique, exports et documentation

- consolidation des exports publics dans `app/evaluation/__init__.py` ;
- `reputation_advisory_to_dict()` / `reputation_advisory_to_json()` ;
- sérialisation JSON-safe des Decimal/enums/dataclasses sans mutation ;
- updater documentaire idempotent pour Evaluation/API/Roadmap ;
- tests d’API publique, d’exports et de préservation documentaire.

## Frontières

Batch 18a ne :
- modifie pas automatiquement `AgentRegistry` ;
- ne fixe pas de seuil de production ;
- n’active pas le LIVE ;
- ne modifie pas le Risk Engine ni le broker ;
- ne considère pas l’ablation comme une preuve causale universelle ;
- ne transforme pas DESIGN/VALIDATION en OOS.

Les campagnes empiriques comparables et les critères opérateur pré-définis restent nécessaires avant
toute décision organisationnelle réelle sur un agent.

<!-- BATCH18B_STEP4_CHANGELOG_START -->

# Batch 18b — Ablation Campaign Runner — clôture

## Livré

- plan de campagne déterministe baseline + `WITHOUT_AGENT` ;
- `run_id` distinct par twin avec fingerprint de comparaison commun ;
- exécution Batch 16/PAPER isolée par variant ;
- conversion automatique en `BacktestPeriodReport` et `AblationComparison` ;
- rejet de toute réutilisation broker/runner entre twins ;
- PAPER Runtime Factory dans `app.services.backtest`, hors couche Evaluation ;
- spécialistes recréés avec un AI Gateway/budget/usage scope propre à chaque variant ;
- modes IA MOCK/CACHED/LIVE_EVAL conservés ;
- export compact JSON/dict du rapport de campagne ;
- exports publics lazy pour éviter les cycles Evaluation ↔ Backtest ;
- aucune mutation `AgentRegistry`, aucun bypass Risk et aucun trading LIVE.

## Clôture Batch 18

Batch 18a + 18b fournissent désormais l'infrastructure complète de réputation et d'ablation.
Une décision organisationnelle réelle reste conditionnée aux campagnes empiriques,
à l'OOS et aux
seuils opérateur pré-définis ; elle n'est jamais appliquée automatiquement.

<!-- BATCH18B_STEP4_CHANGELOG_END -->

<!-- BATCH19_CLOSURE_START -->

# Batch 19 — Recruitment Engine — clôture

## Livré

- contrats `RecruitmentProposal` / `RecruitmentCandidateSpec` et lifecycle candidat séparé ;
- gates déterministes population, fréquence et budget/compute ;
- campagnes twins `BASELINE` / `WITH_CANDIDATE` sur Historical Replay/PAPER ;
- isolation stricte runner/broker entre variantes ;
- comparabilité, provenance et gate OOS ;
- bridge vers `AblationComparison` et réputation multidimensionnelle Batch 18 ;
- distinction coût IA direct candidat / coût IA marginal système ;
- paquet d'évidence auditable et reproductible ;
- advisory `REJECT / EXTEND / PROBATION / RECOMMEND_PROMOTION` ;
- planning de transition opérateur-gaté ;
- audit `FRESH / STALE` et stale-plan guards ;
- exports publics `app.recruitment` ;
- API `GET /api/recruitment/capabilities` en mode `ADVISORY_READ_ONLY` ;
- documentation projet et ADR-026 réalignés.

## Frontières de clôture

Batch 19 ne :
- crée pas automatiquement d'`AgentRegistryEntry` candidat ;
- ne promeut pas automatiquement un candidat vers `ACTIVE` ou `ON_DEMAND` ;
- n'applique pas automatiquement les transitions de lifecycle ;
- ne modifie pas le Risk Engine ;
- n'accorde aucune autorité LIVE ;
- n'expose aucun endpoint HTTP Recruitment d'écriture.

Toute progression matérielle reste opérateur-gatée, fondée sur des critères pré-enregistrés et, pour la promotion, sur une preuve OOS comparable.

## Clôture documentaire

Le layout historique du dépôt est préservé : `01_PROJECT_MASTER.md`, `02_ARCHITECTURE.md` et `07_SECURITE_ET_OPERATIONS.md` restent docs-only et ne sont pas versionnés à la racine.

La prochaine étape de roadmap est **Batch 20 — Task Force Agents**.

<!-- BATCH19_CLOSURE_END -->

<!-- BATCH20_CLOSURE_START -->

# Batch 20 — Task Force dynamique — clôture

## Livré

- contrats Task Force temporaires avec mission, expiration, budget, appels et allowlist ;
- lifecycle `PLANNED → APPROVED_FOR_EXECUTION → RUNNING → terminal` ;
- gates population/capability/compute fail-closed ;
- composition déterministe registry-only ;
- réputation Batch 18 multidimensionnelle sans score magique ;
- provenance de composition, fingerprints et stale detection ;
- clôture de composition vers `TaskForcePlan` toujours `PLANNED` ;
- contrats d’exécution et appels multi-membres via AI Gateway uniquement ;
- comptabilité coût/attempts/latence et arrêt fail-closed ;
- agrégation provenance-preserving, sans vote sémantique ;
- Red Team temporaire optionnel sans remplacer Palermo principal ;
- trigger bridge explicite, sans seuil de complexité inventé ;
- intégration `TaskForceReport` grounded dans le Professor final ;
- Evaluation Task Force et contribution économique uniquement avec baseline comparable ;
- Historical Replay twins `BASELINE` / `WITH_TASK_FORCE` PAPER-only ;
- replay seal et audit `FRESH / STALE` ;
- exports publics consolidés.

## Frontières de clôture

Batch 20 ne :
- sélectionne pas un candidat Recruitment absent d'`AgentRegistry` ;
- ne modifie pas automatiquement le registre ou l’état d’un agent ;
- ne remplace pas le hard budget AI Gateway ;
- n’appelle pas directement un provider IA ;
- ne crée pas directement un `TradeProposal` depuis une Task Force ;
- ne contourne pas Palermo principal ni le Risk Engine ;
- n’accorde aucune autorité LIVE ;
- n’invente aucune métrique économique lorsqu’une baseline comparable est absente.

## Suite

La prochaine étape de roadmap est **Batch 21 — Master Portfolio Layer**. Les bloqueurs LIVE
existants
restent indépendants et doivent toujours être satisfaits avant tout premier ordre réel.

<!-- BATCH20_CLOSURE_END -->

<!-- BATCH22_FRONTEND_V2 -->
## Batch 22 — Frontend V2 / Trading Cockpit

- ajout de `frontend/` Next.js/React/TypeScript strict ;
- cockpit Dashboard/Trading/Backtests/Opportunités/Ordres/Positions/Historique/Agents/Evaluation ;
- `TradingChartAdapter` + Lightweight Charts ;
- Historical Replay et Decision Trace sans recalcul client ;
- API `/api/frontend/v2` minimale, sans capacité LIVE ;
- Settings fail-closed/read-only pour les paramètres sans API backend ;
- tests backend/frontend et documentation `12_FRONTEND_ET_INTERFACE.md` ;
- Dashboard V1 conservé pendant la migration.

<!-- BATCH22_1_BACKTEST_COCKPIT -->
## Batch 22.1 — Backtest Cockpit Completion

- configuration complète du backtest depuis l'UI ;
- édition DESIGN/VALIDATION/OOS alignée sur les bougies ;
- Walk-Forward pilotable ;
- bibliothèque de datasets persistés ;
- persistance V2 des configurations, traces, résumés et exports de replay ;
- aucun changement des frontières PAPER/LIVE ou du Risk Engine.

<!-- DOC_REALIGN_POST_BATCH22_CHANGELOG_START -->

## Alignement documentaire post-Batch 22.1 — 2026-09-15

- état courant réaligné sur `main @ 9f42d3e` ;
- Master Portfolio Layer reflété dans la roadmap/document maître ;
- Frontend V2 / Backtest Cockpit 22.1 et validation pnpm documentés ;
- Prompt Cache OpenAI intégré au corpus permanent et renuméroté ADR-031 pour éviter le conflit avec ADR-026 Recruitment ;
- Market Data utilities `scripts/market_data/` documentés ;
- miroirs racine/`docs/` resynchronisés, notamment `05_MARKET_DATA_ET_EXECUTION.md` ;
- nettoyage des artefacts historiques référencé (`c4ffda0`, `9f42d3e`).

<!-- DOC_REALIGN_POST_BATCH22_CHANGELOG_END -->

<!-- DOCS_SINGLE_SOURCE_20260916 -->
## Normalisation documentaire — source unique `docs/`

- suppression des neuf miroirs historiques de documents permanents à la racine ;
- `docs/` devient la source documentaire canonique unique ;
- `INDEX_ARCHIVE.md` est remplacé par `docs/README.md` ;
- tests Recruitment/Task Force réalignés sur les chemins canoniques ;
- ajout d’ADR-032 pour figer la règle de layout ;
- aucun changement de runtime, Risk Engine, broker ou autorité LIVE.

<!-- BATCH23A1_DECISION_FUNNEL -->
## Batch 23A.1 — Decision Funnel Baseline

- instrumentation Historical Replay strictement observationnelle ;
- agrégation post-hoc Scanner → Compute Gate → IA → Professor → Risk → ordre/fill ;
- reason codes existants normalisés sans changement de prompts ni de seuils ;
- exports `*-decision-funnel.json` et exposition additive dans `PeriodSummary` ;
- garanties de conservation des bougies/scans et non-régression du fingerprint business.

<!-- BATCH23A2_FORWARD_OUTCOMES -->
## Batch 23A.2 — Forward Outcomes

- outcomes post-hoc H1/H3/H5/H10/H20 pour chaque `CandidateOpportunity` ;
- horizons exprimés dans le timeframe de décision, y compris replay MTF ;
- rendement close-to-close, maximum high, minimum low et ordre des extrêmes ;
- gaps et fin de période distingués ; aucune métrique partielle publiée sur horizon incomplet ;
- provenance dataset/run et statut terminal conservés ;
- exports `*-forward-outcomes.json` ;
- aucune donnée Forward Outcomes injectée dans `DecisionContext`, aucun changement Scanner/Professor/Risk/exécution.

<!-- BATCH23A3_FUNNEL_OUTCOME_ATTRIBUTION -->
## Batch 23A.3 — Funnel Outcome Attribution

- croisement post-hoc CandidateOpportunity / Decision Funnel / Forward Outcomes ;
- agrégations descriptives par statut terminal, régime, trigger, Compute Gate, Professor, Risk et échecs ;
- statistiques brutes et directionnelles H1/H3/H5/H10/H20 sans seuil arbitraire ;
- couverture multi-valuée explicite pour triggers, agents sélectionnés et reason codes Risk ;
- limite causale explicite : aucun outcome pour `SCANNER:NO_TRIGGER` ou trigger sous seuil candidat ;
- exports `*-funnel-outcome-attribution.json` ;
- aucun changement Scanner/Professor/Risk/exécution/DecisionContext.

<!-- BATCH23A4_SCANNER_FORWARD_OUTCOMES -->
## Batch 23A.4 — Scanner Forward Outcomes

- Forward Outcomes H1/H3/H5/H10/H20 pour chaque évaluation Scanner ;
- couverture explicite `NO_TRIGGER`, `TRIGGER_BELOW_CANDIDATE_THRESHOLD`, `CANDIDATE_OPPORTUNITY` ;
- score exact, seuil Scanner réellement utilisé et marge au seuil conservés ;
- agrégations descriptives par classification, score exact, trigger et régime ;
- conservation stricte avec Batch 23A.1 Decision Funnel ;
- réutilisation du moteur Forward Outcomes 23A.2 et des mêmes frontières temporelles ;
- exports `*-scanner-forward-outcomes.json` ;
- aucun changement Scanner/Professor/Risk/exécution/DecisionContext.

<!-- BATCH23B1_REPLAY_PERFORMANCE_BASELINE -->
## Batch 23B.1 — Historical Replay Performance Baseline

- baseline : `4368a99944eb04ba3b53cc31f6b379041aa3cbf3` ;
- pool HTTP OpenAI persistant par run + fermeture explicite ;
- instrumentation wall-clock additive du replay et de la couche 23A ;
- exports `*-performance.json` ;
- progression V2 enrichie avec temps écoulé / appels IA ;
- endpoint et bouton d'annulation V2 ;
- aucune modification de logique de décision, seuil, prompt, Risk ou exécution.
<!-- BATCH24A1_CHANGELOG -->
## Batch 24A.1 — Analytics Lab Foundation, Contracts & Isolation Guards

- package `app.analytics` observation-only ;
- identité `AnalyticsLabRun` distincte de `BacktestRun` ;
- provenance dataset/as-of/MTF et `source_cursor_fingerprint` ;
- versions Analytics, snapshots vides, manifeste et SHA-256 déterministes ;
- canonicalisation commune verrouillée par golden test sans changement
  historique attendu ;
- guards AST anti-couplage décisionnel, Forward Outcomes et LIVE ;
- aucune modification fonctionnelle Scanner/DecisionContext/Agents/Risk/PAPER/LIVE.

<!-- BATCH_24A2_RICH_INDICATORS -->
## Batch 24A.2 — Rich Indicators & Parity Catalogue

- registre d'indicateurs Analytics riche, versionné et fingerprinté ;
- snapshots Indicators typés avec warmup/availability explicites ;
- causalité/prefix invariance ;
- parité vérifiée EMA/RSI/MACD/ATR/Bollinger ;
- divergences ADX et Volume Ratio explicites ;
- MFI/CMF/OBV/VWAP/StochRSI/Donchian et rolling ranges ;
- aucune modification du Feature Engine ni du pipeline de décision/trading.

<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Batch 24A.3 — Technical Events

- registry Analytics Technical Events versionné/fingerprinté ;
- 35 événements descriptifs trend/momentum/volatility/trend-strength/volume/structure ;
- détection causale stateless T-1/T avec warmup et égalités explicites ;
- IDs/fingerprints/evidence déterministes ;
- intégration `AnalyticsSnapshot` et identité Analytics ;
- prefix invariance, future malformed isolation, MTF closed-candle semantics et import guards ;
- aucune modification fonctionnelle Scanner/DecisionContext/Agents/Risk/PAPER/LIVE.

<!-- BATCH_24A4_CAUSAL_STRUCTURE_ZIGZAG -->
## Batch 24A.4 — Causal Structure & ZigZag

- projection read-only du Market Structure Money Heist ;
- source structure explicite `MONEY_HEIST_STRUCTURE` ;
- ZigZag causal ATR14 / 2.0 ATR versionné ;
- `pivot_at` et `confirmed_at` distincts ;
- ATR et reversal threshold verrouillés au candidat ;
- policy OHLC conservatrice sans ordre intrabar inventé ;
- IDs/fingerprints déterministes et prefix invariance ;
- aucun changement Scanner/DecisionContext/Agents/Risk/PAPER/LIVE.

<!-- BATCH_24A5_PATTERNS_CAUSAL_LIFECYCLE -->
## Batch 24A.5 — Patterns & Causal Lifecycle

- registry expérimental versionné de 12 patterns adapté de P5.v2 ;
- source primaire de pivots `CAUSAL_ZIGZAG` via contrat source-agnostic `PatternPivot` ;
- lifecycle causal `FORMING / CONFIRMED / FAILED / INVALIDATED` ;
- `detected_at` distinct de l'origine géométrique et aucune back-propagation du statut final ;
- breakout/invalidation sur clôture, policy intrabar conservatrice ;
- IDs stables, state fingerprints évolutifs, provenance des pivots conservée ;
- intégration `AnalyticsSnapshot` et `pattern_registry_version` ;
- observation-only : aucun impact Scanner/DecisionContext/Agents/Risk/PAPER/LIVE/Forward Outcomes ;
- calibration et comparaison de sources réservées au Batch 24A.6.

<!-- BATCH_24A6_PATTERN_CALIBRATION -->
## Batch 24A.6 — Pattern Calibration & Pivot-Source Diagnostics

- calibration observation-only, sans Forward Outcomes ni autorité trading ;
- instrumentation du Pattern Engine canonique : candidats acceptés/rejetés, rule IDs,
  observed/required et raisons ordonnées ;
- identité candidat déterministe, indépendante de P&L/futur ;
- comparaison `CAUSAL_ZIGZAG` vs `MONEY_HEIST_STRUCTURE` avec Pattern Registry constant ;
- adapter Analytics causal pour les strict pivots Money Heist, sans modifier
  `app/market/structure.py` ;
- rapports séparés du `AnalyticsSnapshot`, avec `PatternCalibrationRun` dérivé de
  `AnalyticsLabRun` ;
- DESIGN/VALIDATION/OOS conservés ; acceptance ratio != trading win rate ;
- aucun ranking, auto-tuning, frontend, Contexts/Sequences ou modification des seuils 24A.5.

<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->
## Batch 24A.7 — Causal Contexts & Sequences

- Observation Index causal/read-only sur Indicators, Events, Structure, ZigZag et Pattern transitions ;
- Context DSL v1 immuable/versionné et resolver explicable ;
- Sequence DSL v1 2..10 étapes, strict THEN, fenêtres inclusives à N ;
- research identity séparée de `AnalyticsLabRun`/`BacktestRun` ;
- tests causalité, prefix invariance, ordering, window boundaries et import boundaries ;
- aucune dépendance Forward Outcomes / trading authority.

<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Batch 24B.1 — Opportunity ↔ Analytics Linking

- couche post-hoc `app.evaluation.analytics_attribution` ;
- `DecisionObservationKey` générique réutilisable par 24B.3 ;
- sidecar `OpportunityAnalyticsLink` déterministe ;
- lookup exact de `AnalyticsSnapshot`, sans nearest-time fallback ;
- contrôle BacktestRun/dataset/symbole/timeframe/as_of/MTF policy/cursor ;
- diagnostics explicites missing/mismatch/ambiguous ;
- `DecisionContext` optionnel ;
- business fingerprint et pipelines trading inchangés ;
- architecture guards Analytics/Decision/Attribution renforcés.

<!-- BATCH24FR_AGENT_DIALOGUE -->
## Batch 24-FR — Dialogue agents en français

- ajout du contrat transversal `money-heist.agent-dialogue.fr.v1` ;
- `prompt_render_version` passe à `money-heist.prompt-transport.v3` afin de séparer strictement les replays avant/après changement linguistique ;
- toutes les explications en langage naturel doivent être produites en français (`fr-FR`) ;
- clés JSON, enums, identifiants, références d'évidence et autres tokens machine restent contractuellement inchangés ;
- aucun changement d'autorité trading, Risk Engine, broker ou LIVE ;
- la règle s'applique aussi aux Task Force et autres appels traversant le AI Gateway.

<!-- BATCH24FR2_NATIVE_PROMPTS -->

## Batch 24-FR.2 — French Native Agent Prompts

Les prompts actifs des agents sont désormais écrits nativement en français. Les versions historiques
restent intactes. Versions actives : Professor v7, Palermo v4, Lisbon v2 et spécialistes v6. Task Force
et Master Professor SHADOW utilisent aussi des instructions françaises. Les contrats machine restent
inchangés et `prompt_render_version` passe à `money-heist.prompt-transport.v4`.

<!-- BATCH_24B2_DECISION_INTELLIGENCE_RECORD -->
## Batch 24B.2 — Decision Intelligence Record

- nouvelle couche `app.evaluation.decision_intelligence` read-only ;
- un record déterministe par `CandidateOpportunity` et couple BacktestRun/AnalyticsRun ;
- réutilisation stricte des `OpportunityAnalyticsLink` 24B.1, sans second matching ;
- projections typées du funnel réel et conservation des failures/not-reached ;
- séparation stricte des Forward Outcomes ;
- guards d'architecture anti-retour vers le pipeline de trading ;
- préservation explicite du contrat agents français v1 / prompt transport v4.

<!-- BATCH_24B3_SCANNER_ANALYTICS_ATTRIBUTION -->
## Batch 24B.3 — Scanner ↔ Analytics Attribution Layer

- attribution post-hoc d'un record par ScannerEvaluation ;
- identité canonique `FeatureSnapshot.snapshot_id` ;
- trois classes Scanner State@T partagées avec 23A.4 ;
- extraction du resolver exact 24B.1 sans changement de policy ;
- absence de fallback précédent/futur ;
- conservation stricte du `source_cursor_fingerprint` et de la provenance MTF ;
- références optionnelles cohérentes vers 24B.1 et 24B.2 pour les candidates ;
- IDs/fingerprints/ordre déterministes et guards d'architecture read-only.

<!-- BATCH_24B4_FUNNEL_STAGE_ANALYTICS_ATTRIBUTION -->
## Batch 24B.4 — Funnel Stage ↔ Analytics Attribution

- projection read-only du funnel depuis `DecisionIntelligenceRecord` 24B.2 ;
- stages canoniques Compute Gate, PLAN, Specialist, Palermo, FINAL, TradeProposal, Risk et PAPER ;
- stages fixes `reached`/`not reached` et spécialistes réellement tentés seulement ;
- séparation failure technique / résultat métier ;
- `market_as_of` unique par opportunité et timestamps opérationnels descriptifs ;
- réutilisation stricte du lien Analytics 24B.1, sans second matcher ;
- propagation des diagnostics Analytics unmatched ;
- IDs, fingerprints, ordre et set déterministes ;
- isolation des fingerprints par stage ;
- cross-run guards et architecture guards ;
- aucune dépendance Forward Outcomes, aucun changement du business fingerprint ou du run ID ;
- validation locale complète réussie le 2026-09-17 : Ruff, 24B.1-24B.4, 23A, Decision Funnel / Risk / PAPER, Agents / Orchestration, Analytics et full suite avec exactement 3 skips attendus ;
- Batch 24B.4 et Batch 24B DONE.
