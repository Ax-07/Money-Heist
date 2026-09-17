# Money Heist — Batch 24B.4 — Funnel Stage ↔ Analytics Attribution

**Baseline auditée :** `17eb883486aaff44a62c3587fdd8ee047092af61`
**Commit baseline :** `feat(evaluation): add scanner analytics attribution`
**Schema record :** `money-heist.funnel-stage-analytics-attribution.v1`
**Schema set :** `money-heist.funnel-stage-analytics-attribution-set.v1`
**Policy :** `funnel-stage-analytics-attribution-v1`
**Statut du lot :** DONE - validation locale complète réussie le 2026-09-17
**Autorité :** read-only, post-hoc, observation-only, zéro autorité de trading

## 1. Objectif

24B.4 projette chaque étape du funnel d'une `CandidateOpportunity` à partir du
`DecisionIntelligenceRecord` 24B.2 et lui attache **la même référence Analytics déjà résolue par
24B.1**.

Le batch répond à des questions descriptives du type :

```text
Risk REJECTED
↔ AnalyticsSnapshot exact de la décision
```

ou :

```text
Palermo CAUTION
↔ même état Analytics causal que PLAN / FINAL / Risk
```

Il ne produit aucun jugement de qualité, aucun outcome futur, aucun score de stage et aucun
feedback vers le trading.

## 2. Audit préalable — conclusions

### 2.1 Sources canoniques réutilisées

24B.1 fournit la jointure exacte `OpportunityAnalyticsLink` avec la policy
`opportunity-analytics-exact-v1`.

24B.2 fournit la projection complète par opportunité :

```text
DecisionIntelligenceRecord
  ├─ ComputeGateProjection
  ├─ ProfessorPlanProjection
  ├─ SpecialistsProjection / SpecialistRunProjection[]
  ├─ PalermoProjection
  ├─ ProfessorFinalProjection
  ├─ TradeProposalProjection
  ├─ RiskProjection
  ├─ ExecutionProjection
  ├─ orchestration StageTrace[]
  ├─ PAPER StageTrace[]
  └─ AnalyticsRefProjection
```

24B.3 reste propriétaire de l'attribution de **toutes** les évaluations Scanner, y compris celles
qui ne deviennent jamais `CandidateOpportunity`.

24B.4 ne lit donc ni `AnalyticsLabRun`, ni collection de snapshots Analytics, ni le runtime
Historical Replay pour reconstruire le funnel.

### 2.2 Stages canoniques retenus

L'audit du pipeline réel conduit à la taxonomie analytique suivante :

```text
COMPUTE_GATE
PROFESSOR_PLAN
SPECIALIST / <agent_id>      0..N instances réellement tentées
PALERMO
PROFESSOR_FINAL
TRADE_PROPOSAL
RISK
PAPER
```

Les événements `context`, `task_force_report` et `specialist_contexts` sont des étapes de support
du runtime ; ils ne sont pas promus en stages décisionnels 24B.4.

Le Scanner reste hors de 24B.4 car il est couvert par 24B.3.

### 2.3 TradeProposal

`TRADE_PROPOSAL` est conservé comme stage analytique autonome car :

- l'orchestration possède une projection `TradeProposalProjection` distincte ;
- le pipeline PAPER journalise explicitement `trade_proposal` ;
- le Risk Engine consomme ensuite cet artefact.

24B.4 ne reconstruit jamais FINAL à partir du TradeProposal, ni l'inverse.

### 2.4 PAPER

`PAPER` est un stage analytique unique dans 24B.4. Les sous-événements source
`execution_claim`, `order_intent`, `paper_execution` et les détails broker restent dans
`ExecutionProjection` ; ils ne deviennent pas une nouvelle taxonomie concurrente.

Le record PAPER conserve la référence d'artefact la plus avancée disponible : fill, ordre, puis
client order id.

## 3. REACHED / NOT_REACHED / FAILURE

24B.4 réutilise strictement la sémantique 24B.2.

Pour les stages fixes :

```text
COMPUTE_GATE
PROFESSOR_PLAN
PALERMO
PROFESSOR_FINAL
TRADE_PROPOSAL
RISK
PAPER
```

un record est toujours matérialisé avec `reached=true|false`.

Un stage non atteint ne reçoit jamais un résultat synthétique `NO_TRADE`, `REJECTED` ou
`FAILED`.

Une failure technique n'est attachée à un stage que lorsque la projection 24B.2 indique que ce
stage a réellement été atteint/tenté et que la failure canonique lui appartient. Les failures
restent distinctes des décisions métier.

## 4. Specialists — identité et cardinalité

Les spécialistes ne sont **pas** matérialisés depuis le registry complet.

Un `SPECIALIST` record existe uniquement pour :

- un `SpecialistRunProjection` réellement produit ;
- l'agent explicitement identifié par une failure après sélection, lorsque cette failure est
  conservée par 24B.2.

`stage_instance_id == agent_id` et l'ordre suit exactement `selected_agents` du Professor.
Aucun `specialist_1`, `specialist_2` artificiel n'est créé.

## 5. Politique temporelle

### 5.1 Market causal time

Pour **tous** les stages d'une même opportunité :

```text
stage.market_as_of
=
DecisionIntelligenceRecord.observed_at
```

Lorsque le lien Analytics est `MATCHED` :

```text
stage.analytics_as_of
=
stage.market_as_of
```

La référence `analytics_snapshot_id` est recopiée depuis `DecisionIntelligenceRecord.analytics`,
qui provient lui-même du `OpportunityAnalyticsLink` 24B.1.

### 5.2 Operational time

`operational_at` est seulement un diagnostic opérationnel facultatif.

Les timestamps actuellement fiables dans la projection 24B.2 sont :

- `TradeProposal.created_at` ;
- `RiskDecision.created_at` ;
- `BrokerOrder.created_at/updated_at` ;
- `Fill.filled_at`.

Les timestamps wall-clock des `PipelineAuditEvent` ne sont pas réintroduits : 24B.2 les a
volontairement exclus de ses `StageTrace` car ils sont volatils et non causaux.

Donc :

```text
market_as_of = 12:00:00
TradeProposal.created_at = 12:00:02
Risk.created_at = 12:00:06
Fill.filled_at = 12:00:07
```

reste une seule décision de marché attribuée à :

```text
AnalyticsSnapshot @ 12:00:00
```

Aucun timestamp opérationnel ne déclenche un lookup Analytics.

## 6. Contrats publics

Le batch ajoute :

- `FunnelStage` ;
- `FunnelStageAnalyticsAttributionRecord` ;
- `FunnelStageAnalyticsAttributionSet` ;
- `project_funnel_stage_analytics_records()` ;
- `build_funnel_stage_analytics_attribution()`.

Un record contient notamment :

```text
record_id / record_fingerprint
source_backtest_run_id
analytics_run_id
decision_intelligence_record_id
opportunity_id
stage / stage instance
reached / source stage status / source result
market_as_of / operational_at optionnel
source projection fingerprint
source artifact ref optionnelle
24B.1 link identity/status
AnalyticsSnapshot ref optionnelle
```

Le payload Analytics complet n'est jamais copié.

## 7. Identité et fingerprints

L'identité d'un stage est déterministe sur :

```text
schema / policy
source BacktestRun
AnalyticsRun
DecisionIntelligenceRecord id
opportunity id
stage
stage_instance_id éventuel
```

Le `record_fingerprint` couvre uniquement les faits matériels du stage et son attribution
Analytics. Il **n'inclut pas** le fingerprint global du `DecisionIntelligenceRecord` afin qu'une
modification de Palermo ne fasse pas artificiellement changer le fingerprint du stage Risk ou
PLAN si leur projection propre reste identique.

Le `decision_intelligence_record_fingerprint` reste néanmoins conservé comme provenance.

`source_projection_fingerprint` est calculé sur la projection 24B.2 du stage. Aucun faux
fingerprint d'artefact source n'est fabriqué lorsqu'un contrat source n'en possède pas.

## 8. Analytics unmatched

Un lien 24B.1 non `MATCHED` ne supprime jamais le funnel.

Chaque stage conserve :

```text
analytics_link_id
analytics_link_status
analytics_snapshot_id = None
analytics diagnostics
```

24B.4 ne tente aucun rematching, nearest-time lookup, fallback précédent ou snapshot futur.

## 9. Cohérence et cross-run

Le builder de set vérifie que tous les `DecisionIntelligenceRecord` appartiennent au même :

```text
source_backtest_run_id
analytics_run_id
```

que leur `DecisionIntelligenceRecordSet`.

Les références internes plus fines ont déjà été validées par 24B.2. 24B.4 ne contourne pas ces
contrats et ne recherche aucun artefact libre par timestamp.

## 10. Coverage

`FunnelStageAnalyticsAttributionSet` expose :

```text
decision_record_count
covered_decision_record_count
stage_record_count
reached_stage_count
not_reached_stage_count
matched_analytics_stage_count
unmatched_analytics_stage_count
```

La coverage mesure l'intégrité de la projection, jamais la qualité ou la performance trading.

## 11. Isolation

Le sens des dépendances est uniquement :

```text
24B.1 Analytics link
        ↓
24B.2 DecisionIntelligenceRecord
        ↓
24B.4 Funnel Stage Attribution
```

Interdictions garanties par tests :

- Scanner / DecisionContext / Agents / Orchestration / Risk / PAPER / LIVE n'importent pas 24B.4 ;
- `app.analytics` n'importe pas `app.evaluation` ;
- 24B.4 n'importe ni Analytics Core, ni Scanner, ni services actifs Agents/Risk/PAPER/LIVE ;
- aucune dépendance vers Forward Outcomes, Scanner Forward Outcomes ou Funnel Outcome Attribution ;
- aucun appel OpenAI, agent, RiskEngine, PaperBroker ou broker LIVE.

## 12. Séparation avec Batch 23A

```text
24B.4 : stage @ T ↔ Analytics @ T
23A   : decision/stage @ T ↔ Forward Outcome after T
```

Les deux axes restent séparés afin de permettre plus tard 24D sans contamination causale.

## 13. Tests du lot

Le lot couvre notamment :

- Compute Gate stop ;
- plusieurs Specialists et ordre déterministe ;
- specialist failure ;
- Palermo CLEAR / CAUTION / REJECT ;
- FINAL NO_TRADE ;
- Risk APPROVED / RESIZED / REJECTED ;
- PAPER success / technical failure ;
- même Analytics snapshot pour tous les stages ;
- timestamps opérationnels plus tardifs sans rematching ;
- Analytics unmatched ;
- déterminisme ID/fingerprint/ordre/set ;
- changement matériel isolé d'un stage ;
- changement de référence Analytics ;
- contamination cross-run ;
- spécialistes dupliqués ;
- non-mutation de l'identité source ;
- guards d'architecture.

## 14. Hors scope

24B.4 n'ajoute pas :

- API/UI 24C ;
- overlays TradingView ;
- rapports 24D ;
- scoring de qualité ;
- Forward Outcomes ;
- PnL/MFE/MAE futur ;
- tuning des agents/Scanner/Risk ;
- modification de prompts ;
- injection Analytics dans DecisionContext ;
- changement du `BacktestRun.run_id` ou du business fingerprint.

## 15. Clôture

La validation locale complète a réussi le 2026-09-17 : Ruff, tests 24B.1-24B.4, régressions Batch 23A Forward Outcomes, Decision Funnel / Risk / PAPER, Agents / Orchestration, tests/analytics et suite complète. La suite complète comporte exactement les 3 skips attendus.

Batch 24B.4 et Batch 24B sont donc DONE sur cette baseline.
