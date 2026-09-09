# Money Heist — API et Modèles de Données

**Document :** Contrats, schémas et API internes  
**Version :** 0.1  
**Statut :** Spécification conceptuelle

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


## 20. Addendum Batch 17a — contrats Rio / Denver

Nouveaux contrats internes principaux :
- `RioContext` : provenance dérivés, instrument, timestamp, stale/quality et métriques disponibles ;
- `DenverContext` : `stats_id`, version de setup, `as_of`, provenance runs/datasets, sample counts et
  métriques statistiques ;
- `RioAnalysis` et `DenverAnalysis` : sorties strictes de spécialistes ;
- `HistoricalSetupKey` / `HistoricalSetupObservation` / `HistoricalSetupStats` ;
- `HistoricalSetupStatsCatalog` : base content-addressed exportable/importable ;
- `DenverSetupStatsContextProvider` : adaptateur read-only vers l’orchestration ;
- `SpecialistContextProvider` : port déterministe facultatif par opportunité.

Les contextes spécialistes ne sont pas des tool calls LLM. Ils sont préparés par du code backend et
validés avant que le Professor ne voie l’agent comme disponible. Une collision entre contexte fourni
par un provider et contexte explicite pour le même agent est rejetée.

## 21. Addendum Batch 17b — modèles Market Data et observabilité Rio

Nouveaux contrats internes :
- `DerivativesPositioningSnapshot` : faits dérivés normalisés, sans recommandation ;
- `KrakenFuturesAnalyticsConfig` / `KrakenFuturesAnalyticsProvider` ;
- `MarketSidecarRefresher` ;
- `MarketSidecarRefreshResult` / `MarketSidecarRefreshStatus` ;
- `PaperShadowMarketInput.sidecar_refreshes` et lookup `sidecar_result(refresher_id)` ;
- `KrakenFuturesRioContextProvider` ;
- `RioContextDiagnostic` / `RioContextDiagnosticStatus` ;
- `CompositeSpecialistContextProvider` pour combiner plusieurs sources spécialisées sans collision.

Aucun de ces contrats n'est une API d'exécution. Les diagnostics Rio sont read-only et ne provoquent
aucun I/O lorsqu'ils sont consultés.
