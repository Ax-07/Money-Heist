# Money Heist — API et Modèles de Données

**Document :** Contrats, schémas et API internes  
**Version :** 0.4
**Statut :** Référence active — contrats et API intégrés

---

## 1. Objectif

Définir les objets métier stables autour desquels le code sera construit.

Les champs exacts pourront évoluer, mais les responsabilités doivent rester séparées.

---

## 2. Conventions

- identifiants UUID ou équivalent stable ;
- timestamps UTC ;
- enums explicites ;
- montants avec précision adaptée ;
- aucune donnée secrète dans les modèles métier ;
- version de schéma pour objets persistés critiques.

---

## 3. SystemConfig

```json
{
  "system_id": "balanced_v1",
  "mode": "PAPER",
  "risk_profile_id": "balanced",
  "ai_budget_id": "prototype",
  "symbols": ["BTC...", "ETH...", "SOL..."]
}
```

Les symboles définitifs dépendent de l’exchange choisi.

---

## 4. MarketSnapshot

```json
{
  "snapshot_id": "uuid",
  "symbol": "string",
  "source": "string",
  "observed_at": "timestamp",
  "received_at": "timestamp",
  "features": {},
  "quality": {
    "is_stale": false,
    "missing_fields": []
  }
}
```

---

## 5. CandidateOpportunity

```json
{
  "opportunity_id": "uuid",
  "snapshot_id": "uuid",
  "system_id": "string",
  "symbol": "string",
  "priority_score": 0,
  "triggers": [],
  "created_at": "timestamp",
  "expires_at": "timestamp"
}
```

---

## 6. AgentRequest

```json
{
  "request_id": "uuid",
  "opportunity_id": "uuid",
  "agent_id": "berlin",
  "round": 1,
  "prompt_version": "string",
  "model_route": "string"
}
```

---

## 7. AgentAnalysis

```json
{
  "analysis_id": "uuid",
  "request_id": "uuid",
  "agent_id": "berlin",
  "stance": "LONG",
  "confidence": 0.72,
  "evidence": [],
  "risks": [],
  "invalidation": [],
  "created_at": "timestamp"
}
```

---

## 8. AIUsageRecord

```json
{
  "usage_id": "uuid",
  "agent_id": "string",
  "model_id": "string",
  "input_tokens": 0,
  "cached_input_tokens": 0,
  "output_tokens": 0,
  "estimated_cost": 0.0,
  "currency": "EUR",
  "latency_ms": 0,
  "created_at": "timestamp"
}
```

Le calcul de coût doit être centralisé.

---

## 9. TradeProposal

```json
{
  "proposal_id": "uuid",
  "opportunity_id": "uuid",
  "system_id": "string",
  "symbol": "string",
  "side": "LONG",
  "confidence": 0.74,
  "entry": {},
  "stop": {},
  "targets": [],
  "expected_rr": 2.0,
  "thesis": [],
  "invalidation": [],
  "expires_at": "timestamp"
}
```

---

## 10. RiskProfile

```json
{
  "risk_profile_id": "balanced",
  "max_risk_per_trade_pct": null,
  "max_daily_loss_pct": null,
  "max_drawdown_pct": null,
  "max_portfolio_risk_pct": null,
  "max_positions": null,
  "max_leverage": null
}
```

Les `null` représentent les décisions encore ouvertes dans la spécification actuelle.

---

## 11. RiskDecision

```json
{
  "risk_decision_id": "uuid",
  "proposal_id": "uuid",
  "status": "APPROVED",
  "reason_codes": [],
  "approved_quantity": 0.0,
  "approved_risk_amount": 0.0,
  "created_at": "timestamp"
}
```

---

## 12. OrderIntent

Objet interne créé uniquement après RiskDecision autorisée.

```json
{
  "order_intent_id": "uuid",
  "risk_decision_id": "uuid",
  "system_id": "string",
  "symbol": "string",
  "side": "BUY",
  "order_type": "MARKET",
  "quantity": 0.0
}
```

---

## 13. BrokerOrder

```json
{
  "broker_order_id": "uuid",
  "client_order_id": "string",
  "external_order_id": null,
  "mode": "PAPER",
  "status": "SUBMITTED",
  "submitted_at": "timestamp"
}
```

---

## 14. Fill

```json
{
  "fill_id": "uuid",
  "broker_order_id": "uuid",
  "price": 0.0,
  "quantity": 0.0,
  "fee": 0.0,
  "filled_at": "timestamp"
}
```

---

## 15. Position

```json
{
  "position_id": "uuid",
  "system_id": "string",
  "symbol": "string",
  "side": "LONG",
  "quantity": 0.0,
  "average_entry": 0.0,
  "realized_pnl": 0.0,
  "unrealized_pnl": 0.0,
  "status": "OPEN"
}
```

---

## 16. SafetyEvent

```json
{
  "event_id": "uuid",
  "severity": "CRITICAL",
  "code": "DAILY_LOSS_LIMIT",
  "system_id": "string",
  "details": {},
  "created_at": "timestamp"
}
```

---

## 17. AgentRegistryEntry

```json
{
  "agent_id": "rio",
  "role": "derivatives",
  "state": "ON_DEMAND",
  "prompt_version": "v1",
  "allowed_tools": [],
  "budget_policy_id": "default"
}
```

---

## 18. RecruitmentProposal

```json
{
  "recruitment_id": "uuid",
  "proposed_name": "Marseille",
  "role": "liquidation_specialist",
  "hypothesis": "string",
  "required_data": [],
  "allowed_tools": [],
  "success_metrics": [],
  "max_budget": 0.0,
  "status": "PROPOSED"
}
```

---

## 19. Experiment

```json
{
  "experiment_id": "uuid",
  "name": "Professor v4 vs v3",
  "baseline": "string",
  "variant": "string",
  "primary_metric": "string",
  "status": "RUNNING"
}
```

---

## 20. Endpoints API V1 envisagés

### Health

```text
GET /health
GET /ready
```

### Système

```text
GET /systems
GET /systems/{id}
```

### Marché

```text
GET /market/snapshots
GET /opportunities
```

### Agents

```text
GET /agents
GET /agents/{id}
GET /analyses
```

### Trading

```text
GET /positions
GET /orders
GET /trades
```

### Performance

```text
GET /performance
GET /ai-costs
```

### Sécurité

```text
POST /safety/stop-new-trades
```

Les endpoints d’écriture sensibles exigeront des contrôles d’accès adaptés.

---

## 21. API interne des agents

Les agents ne consomment pas arbitrairement l’API HTTP.

Ils utilisent une couche de tools autorisés.

Exemples :

- `get_market_context` ;
- `get_portfolio_summary` ;
- `get_agent_statistics` ;
- `get_historical_setup_stats`.

---

## 22. Validation

Tous les objets critiques sont validés avant stockage ou utilisation.

Technologie prévue côté Python :

- modèles typés ;
- validation de schéma ;
- erreurs explicites.

Le choix exact de bibliothèque sera décidé dans Batch 01.

---

## 23. Compatibilité

Les objets persistés critiques doivent pouvoir évoluer.

Prévoir :

- migrations DB ;
- champ version lorsque utile ;
- convertisseurs si un schéma change.

---

## 24. Critères d’acceptation

- TradeProposal ne contient aucun secret ;
- OrderIntent ne peut exister sans RiskDecision ;
- SHADOW ne peut créer un ordre LIVE valide ;
- chaque analyse référence sa version de prompt ;
- chaque coût IA est lié à une exécution ;
- chaque décision peut être reliée à son snapshot.

---

## 18. Addendum Batch 16 — modèles de backtest

Contrats principaux ajoutés :

- `DatasetRef` : identité/version/hash du dataset ;
- `BacktestConfig` : système, versions, mode IA, coûts d’exécution, policy intrabar, `code_version`, `execution_model_version`, `random_seed` ;
- `BacktestRun` / `BacktestResult` ;
- `HistoricalReplayPoint` / `HistoricalReplayResult` ;
- `HistoricalTradeProtection` / `HistoricalExitEvent` ;
- `BacktestAIContext` / `BacktestResponseCache` ;
- `BacktestBusinessFingerprint` ;
- `BacktestPeriodRole` (`DESIGN`, `VALIDATION`, `OOS`) ;
- `BacktestSplitPlan` / `BacktestRunSet` ;
- `BacktestPeriodReport` / `BacktestSplitReport` ;
- `WalkForwardPlan` / `WalkForwardWindow` / `WalkForwardReport` ;
- `BacktestRunManifest`.

Les exports JSON destinés à la reproductibilité utilisent une canonicalisation stable des datetimes UTC, Decimal, enums, dataclasses et mappings triés.

---

## 19. Addendum Batch 16.7 — API Backtest Dashboard

Endpoints opérateur :

```text
GET  /dashboard/backtest
GET  /api/dashboard/backtest/capabilities
POST /api/dashboard/backtest/dataset/preview
POST /api/dashboard/backtest/runs
GET  /api/dashboard/backtest/runs
GET  /api/dashboard/backtest/runs/{campaign_id}
GET  /api/dashboard/backtest/runs/{campaign_id}/exports/{name}
GET  /api/dashboard/backtest/ai-cache
POST /api/dashboard/backtest/ai-cache
```

Le payload de campagne contient dataset CSV, splits, `RiskProfile`, `MarketConstraints`, paramètres PAPER, mode IA et walk-forward optionnel. Aucun champ de clé API fournisseur n'est accepté.


---

## 25. Addendum Batch 19 — modèles et API Recruitment

### 25.1 Contrats publics

Le package `app.recruitment` expose notamment :
- `RecruitmentProposal` ;
- `RecruitmentCandidateSpec` / `RecruitmentBaselineSpec` / `RecruitmentSuccessCriterion` ;
- `RecruitmentCandidateState` ;
- lifecycle records et transition plans ;
- `RecruitmentCapacityPolicy` / snapshot / décisions de gate ;
- plan et exécution de campagne candidate ;
- gate de comparabilité/provenance/OOS ;
- bridge vers `AblationComparison` Batch 18 ;
- réputation/coûts candidat ;
- `RecruitmentCandidateEvidencePackage` ;
- `RecruitmentAdvisory` ;
- planning advisory → lifecycle ;
- `RecruitmentAdvisoryAuditRecord` et guards de fraîcheur/reproductibilité.

États candidat :

```text
PROPOSED
CANDIDATE
SHADOW
PROBATION
REJECTED
PROMOTION_RECOMMENDED
```

Avis :

```text
REJECT
EXTEND
PROBATION
RECOMMEND_PROMOTION
```

Purposes d'évidence : `DIAGNOSTIC` et `PROMOTION`. Fraîcheur d'audit : `FRESH` / `STALE`. Statut de planning : `READY` / `BLOCKED`.

### 25.2 API HTTP Recruitment V1

Endpoint public livré :

```text
GET /api/recruitment/capabilities
```

Réponse `batch19.recruitment-api.v1`, mode `ADVISORY_READ_ONLY`.

La réponse publie les enums/actions/métriques supportés, les versions de contrats et les drapeaux de sécurité. Elle indique explicitement :
- `operator_authorization_required = true` ;
- `auto_apply = false` ;
- `registry_mutation = false` ;
- `lifecycle_transition_applied = false` ;
- `promotion_applied = false` ;
- `live_authority = false`.

Aucun endpoint Recruitment `POST`, `PUT`, `PATCH` ou `DELETE` n'est livré dans Batch 19e.1.

<!-- BATCH20_API_START -->

## Addendum Batch 20 — Contrats Task Force

Contrats publics principaux de `app.task_force` :
- `TaskForceRequest`, `TaskForceOperatorPolicy`, `TaskForcePlan` ;
- `TaskForceLifecycleRecord`, `TaskForceTransitionPlan` ;
- `TaskForcePlanGateDecision`, `TaskForceComputeDecision` ;
- `TaskForceCompositionPolicy`, `TaskForceCompositionResult` ;
- `TaskForceCompositionProvenance`, `TaskForceCompositionAudit` ;
- `TaskForceCompositionClosure` ;
- `TaskForceExecutionContract`, `TaskForceMemberExecutionSpec` ;
- `TaskForceMultiMemberExecution` et records d’usage ;
- `TaskForceReport` et contributions agrégées.

Bridges publics orchestration :
- `TaskForceTriggerSignal`, `TaskForceInvocationPolicy`, `TaskForceInvocationDecision` ;
- `TaskForceReportIntegration` ;
- `evaluate_task_force_trigger()` ;
- `prepare_task_force_report_for_orchestration()`.

Contrats publics Evaluation :
- `TaskForceRunOutcome`, `TaskForceOutcomeComparison`, `TaskForceEvaluationReport` ;
- `TaskForceReplayPlan`, `TaskForceReplayCampaignReport`, `TaskForceReplayExecutor` ;
- `TaskForceReplaySeal`, `TaskForceReplayAudit` et audit `FRESH / STALE`.

Les contrats d’autorité utilisent des littéraux/flags fail-closed (`registry_mutation=False`,
`risk_authority=False`, `live_authority=False`).

<!-- BATCH20_API_END -->

<!-- BATCH22_FRONTEND_V2 -->
## Addendum Batch 22 — API Frontend V2

Endpoints opérateur supplémentaires :

```text
GET  /api/frontend/v2/capabilities
GET  /api/frontend/v2/market/candles
GET  /api/frontend/v2/market/constraints
POST /api/frontend/v2/backtests/runs
GET  /api/frontend/v2/backtests/runs/{campaign_id}/replay
```

Le premier endpoint ne retourne aucune valeur secrète et indique explicitement que les contrôles LIVE HTTP ne sont pas exposés. Le endpoint market réutilise le provider public Kraken existant. Le lancement backtest délègue à `BacktestDashboardService`. Le replay V2 assemble le dataset de la requête, les `AgentTraceView` existantes, les exports closed-trades et equity déjà produits ; il ne réexécute aucune décision historique.

<!-- BATCH22_1_BACKTEST_COCKPIT -->
## Addendum Batch 22.1 — API Backtest Cockpit

L'API V2 ajoute une bibliothèque de datasets, le lancement par `dataset_id`, le listing/détail/progress/configuration persistants et le replay durable. Le CSV reste côté backend et n'est pas renvoyé au navigateur pour réutilisation.

<!-- DOC_REALIGN_PROMPT_CACHE_API_START -->

## Addendum 2026-09-15 — contrats Prompt Cache AI Gateway

Le AI Gateway expose une policy explicite :

```text
PromptCacheMode = DISABLED | OPENAI_EXPLICIT
PromptCacheCapability = NONE | OPENAI_EXPLICIT
PromptCachePolicy(mode, ttl=30m, prompt_cache_key?)
```

Une route ne peut activer `OPENAI_EXPLICIT` que si elle déclare la capability correspondante et utilise le provider OpenAI. Le mode n’est jamais inféré depuis le nom du modèle.

`AIGatewayRequest`/`ProviderRequest` transportent la version de rendu, le préfixe cacheable/fingerprint de schéma et la policy. `ProviderResponse` peut retourner les diagnostics de cache. `TokenUsage` sépare input normal, read, write et output.

Le transport courant est `money-heist.prompt-transport.v2`.

<!-- DOC_REALIGN_PROMPT_CACHE_API_END -->

<!-- BATCH23A1_API_MODELS -->
## Addendum Batch 23A.1 — modèles Decision Funnel

Contrats publics ajoutés sous `app.evaluation.decision_funnel` :
- `DecisionFunnelObservationCounts` ;
- `DecisionFunnelCounts` ;
- `DecisionFunnelReasonCount` ;
- `DecisionFunnelPostHoc` ;
- `DecisionFunnelReport`.

Le rapport expose notamment :
- bougies évaluées et skips pré-Scanner ;
- évaluations Scanner, no-trigger, triggered, opportunités ;
- Compute Gate allowed/blocked ;
- orchestrations IA déclenchées ;
- `NO_ANALYSIS`, `NO_TRADE`, échecs d'orchestration ;
- `TradeProposal` créées ;
- Risk `REJECTED` / `RESIZED` / `APPROVED` ;
- ordres soumis et fills ;
- reason codes agrégés et triés de manière déterministe ;
- closed trades / ordres broker / fills broker dans une section `post_hoc`.

`PeriodSummary.decision_funnel` est optionnel afin que les anciens `summary.json` restent lisibles. Les nouveaux exports sont `design-decision-funnel.json`, `validation-decision-funnel.json` et `oos-decision-funnel.json`.

Le schéma du Decision Funnel est observationnel : il n'est pas une entrée de `BacktestConfig`, ne change pas `run_id` et n'est jamais une entrée de décision.

<!-- BATCH23A2_4_API_MODELS -->
## Addendum Batch 23A.2–23A.4 — contrats de mesure causale

### Forward Outcomes

Contrats sous `app.evaluation.forward_outcomes` :

- `ForwardOutcomeReference` ;
- `ForwardOutcomeHorizon` ;
- `ForwardOutcomeRecord` ;
- `ForwardOutcomeStatusCount` ;
- `ForwardOutcomeHorizonSummary` ;
- `ForwardOutcomeSummary` ;
- `ForwardOutcomeReport`.

`ForwardOutcomeReport` conserve provenance dataset/run, timeframe source, timeframe de décision, bornes de période, horizons et records déterministes. Un horizon incomplet contient uniquement ses métadonnées d'incomplétude ; aucune métrique de prix partielle n'est publiée.

### Funnel Outcome Attribution

Contrats sous `app.evaluation.funnel_outcome_attribution` :

- `FunnelOutcomeSubject` ;
- `FunnelOutcomeHorizonStats` ;
- `FunnelOutcomeGroup` ;
- `FunnelOutcomeDimensionCoverage` ;
- `FunnelOutcomeAttributionCoverage` ;
- `FunnelOutcomeAttributionReport`.

Dimensions disponibles : statut terminal, régime, trigger Scanner, reason Compute Gate, Professor PLAN, agent sélectionné, échec orchestration, direction Professor FINAL, side de proposition, statut/reason Risk et échec Paper Pipeline.

Les dimensions `SCANNER_TRIGGER`, `SELECTED_AGENT` et `RISK_REASON` sont multi-valuées et ne doivent pas être sommées comme des partitions exclusives.

### Scanner Forward Outcomes

Contrats sous `app.evaluation.scanner_forward_outcomes` :

- `ScannerOutcomeClassification` ;
- `ScannerOutcomeGroupDimension` ;
- `ScannerForwardOutcomeReference` ;
- `ScannerForwardOutcomeRecord` ;
- `ScannerOutcomeHorizonStats` ;
- `ScannerOutcomeGroup` ;
- `ScannerOutcomeDimensionCoverage` ;
- `ScannerForwardOutcomeSummary` ;
- `ScannerForwardOutcomeReport`.

Classes exclusives :
- `NO_TRIGGER` ;
- `TRIGGER_BELOW_CANDIDATE_THRESHOLD` ;
- `CANDIDATE_OPPORTUNITY`.

Chaque record conserve le score Scanner exact, `min_priority_score`, `score_margin_to_threshold`, triggers, régime et éventuel `candidate_opportunity_id`.

### Exports de campagne

Par split :

- `*-decision-funnel.json` ;
- `*-forward-outcomes.json` ;
- `*-funnel-outcome-attribution.json` ;
- `*-scanner-forward-outcomes.json`.

Ces contrats sont additifs et observationnels. Ils ne sont pas des entrées de `BacktestConfig`, ne changent pas `run_id`, n'entrent jamais dans le `DecisionContext` de la décision évaluée et ne déplacent aucune autorité Risk/LIVE.
<!-- BATCH24A1_MODELS -->
## Contrats Analytics Lab — Batch 24A.1

Contrats ajoutés : `AnalyticsComponentVersions`, `AnalyticsAsOfInput`,
`AnalyticsLabRun`, `AnalyticsSnapshot`, `AnalyticsLabManifest` et
`AnalyticsObservationProvenance`.

Invariants : timestamps timezone-aware/UTC, SHA-256 validés,
`source_cursor_fingerprint` conservé, rôle DESIGN/VALIDATION/OOS explicite, IDs
et digests déterministes. `components={}` est valide tant qu'aucun moteur
Analytics n'est installé.

Aucun champ Analytics n'est ajouté à `CandidateOpportunity` ni à
`DecisionContextV1` dans ce batch.

<!-- BATCH_24A2_RICH_INDICATORS -->
### Batch 24A.2 — Analytics Indicator contracts

24A.2 adds typed `IndicatorValue` and `AnalyticsIndicatorSnapshot` contracts. The snapshot preserves symbol, timeframe, `as_of`, `source_cursor_fingerprint`, registry version/fingerprint, warmup/availability states and a deterministic snapshot fingerprint. It is embedded in the 24A.1 `AnalyticsSnapshot` under the typed `indicators` component.

<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Addendum Batch 24A.3 — TechnicalEventObservation

Contrats Analytics ajoutés : `TechnicalEventDefinition`, `TechnicalEventEvidence` et
`TechnicalEventObservation`. Une observation contient une identité déterministe, le run
Analytics, type/famille/direction descriptive, symbole/timeframe, `event_at`,
`available_at`, fingerprints source/cursor, evidence T-1/T, version de définition et
`event_fingerprint`. Les événements sont sérialisables et n'ont aucune sémantique
`LONG`/`SHORT`.

<!-- BATCH_24A4_CAUSAL_STRUCTURE_ZIGZAG -->
## Addendum Batch 24A.4 — Structure / ZigZag

Contrats ajoutés : `StructureSource`, `AnalyticsMarketStructureObservation`,
`CausalZigZagInputBar`, `CausalZigZagPivot` et registry ZigZag versionné.
Les pivots portent `pivot_at`, `confirmed_at`, prix, ATR verrouillé, seuil,
amplitudes, nombre de barres, provenance indicator/cursor, ID et fingerprint.

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
