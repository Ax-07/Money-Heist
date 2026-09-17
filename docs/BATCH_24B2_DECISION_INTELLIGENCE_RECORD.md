# Money Heist — Batch 24B.2 Decision Intelligence Record

**Baseline auditée :** `6755266b8e5bd0e8c9d4287914ceb8ee68dec16b`
**Commit de clôture 24B.1 présent dans l'historique :** `31bf2ef062ae5a4aa024279cf283d79223103c83`
**Schema record :** `money-heist.decision-intelligence-record.v1`
**Policy :** `decision-intelligence-projection-v1`
**Autorité :** read-only, post-hoc, replay-derived, zéro autorité de trading

## 1. But

24B.2 construit une projection déterministe d'une `CandidateOpportunity` et de la chaîne de
décision réellement produite pour cette opportunité, puis lui attache exclusivement la référence
Analytics déjà résolue par 24B.1.

Le record répond à la question :

> Qu'est-ce que Money Heist a observé, quelles étapes ont réellement été atteintes, qu'ont produit
> les agents/Risk/PAPER, et quel `AnalyticsSnapshot` 24B.1 a lié au même instant causal ?

Il ne répond pas encore à la question de savoir si la décision était bonne ou mauvaise.

## 2. Sources canoniques auditées

La projection s'appuie sur les artefacts existants :

```text
HistoricalReplayPoint
  ├─ ScanResult / CandidateOpportunity
  ├─ DecisionContextV1 (facultatif)
  └─ PaperPipelineResult
       ├─ OrchestrationResult
       │    ├─ ComputeGateDecision
       │    ├─ ProfessorPlan
       │    ├─ SpecialistRunRecord[]
       │    ├─ PalermoRunRecord
       │    ├─ ProfessorFinalDecision
       │    ├─ TradeProposal
       │    ├─ AgentCallAudit[]
       │    └─ PipelineAuditEvent[]
       ├─ RiskDecisionRecord
       ├─ PaperOrderIntent
       ├─ BrokerOrder
       ├─ Fill
       └─ PaperPipelineEvent[]

OpportunityAnalyticsLink (24B.1)
  └─ AnalyticsSnapshotRef éventuel
```

Le `DecisionFunnelReport` 23A est un agrégat de compteurs et raisons ; il n'est pas un record
par opportunité. 24B.2 peut l'utiliser comme validation de cohérence du run et du nombre de
candidats, mais ne le transforme pas en seconde machine d'état.

## 3. Décisions d'architecture 24B.2

1. Le namespace est `app.evaluation.decision_intelligence`.
2. Un record existe aussi lorsque le lien Analytics 24B.1 n'est pas `MATCHED`.
3. `DecisionContextV1` est conservé par référence/identité, pas recopié intégralement.
4. Les sorties agents sont projetées depuis les traces canoniques sans appel IA supplémentaire.
5. L'exécution ne contient que les faits immédiats PAPER de la décision à T ; aucun résultat futur.
6. Un `DecisionIntelligenceRecordSet` est fourni pour préparer 24C sans ajouter d'API.
7. `reached` décrit l'étape réellement tentée ; `SKIPPED` reste un statut source et n'est pas
   transformé en `NO_TRADE` ou `REJECTED`.
8. `record_id` dépend du run source, du run Analytics, de l'opportunité et du `link_id` 24B.1.
9. Les spécialistes conservent l'ordre d'orchestration du Professor, qui est matériel dans le
   pipeline actuel et dans `TradeProposal.specialist_request_ids`.
10. Le statut canonique global par opportunité est celui de `PaperPipelineResult` et le statut
    orchestration est celui de `OrchestrationResult`; aucun nouveau `terminal_status` n'est inventé.

## 4. Identité et fingerprint

Le `record_id` est déterministe pour :

```text
schema/policy
+ source_backtest_run_id
+ analytics_run_id
+ opportunity_id
+ opportunity_analytics_link_id
```

Le `record_fingerprint` couvre la projection matérielle : Scanner, référence DecisionContext,
Compute Gate, PLAN, spécialistes, Palermo, FINAL, TradeProposal, Risk, exécution immédiate,
traces d'étapes, failures et référence Analytics 24B.1. Les traces conservent séquence, stage et
statut, mais pas le `created_at` opérationnel des `PipelineAuditEvent`, actuellement volatile et
non causal dans l'orchestration.

Les objets sources n'exposant pas de fingerprint canonique propre ne reçoivent pas un faux
fingerprint. Leur contenu projeté est canonicalisé via `app.common.canonical`.

## 5. Etapes non atteintes et failures

Le record distingue explicitement :

```text
not reached
reached + completed
reached + failed
skipped par le pipeline source
```

Une failure technique reste une failure technique. Elle n'est jamais remplacée par une stance
`NEUTRAL`, un `NO_TRADE` ou un rejet Risk synthétique.

Exemples :

```text
Compute Gate SKIP_AI
→ PLAN non atteint
→ spécialistes non atteints
→ Palermo non atteint
→ FINAL non atteint
→ Risk non atteint
→ execution non atteinte
```

```text
Specialists STARTED
→ Berlin success
→ Tokyo provider failure
→ orchestration FAILED
```

Le record conserve le run Berlin réellement produit et la failure Tokyo ; il ne fabrique aucun
résultat pour Tokyo.

## 6. Frontière Analytics

24B.2 reçoit un `OpportunityAnalyticsLinkSet` déjà construit. Son API n'accepte ni
`AnalyticsLabRun`, ni collection de snapshots Analytics. Le builder ne peut donc pas exécuter un
second matching.

Pour un lien `MATCHED`, il conserve :

```text
link_id / link_fingerprint / link policy
analytics_run_id
analytics_snapshot_id
analytics_snapshot_fingerprint
analytics_as_of
source_cursor_fingerprint (côté décision)
analytics_snapshot_source_cursor_fingerprint (si snapshot présent)
```

Pour un lien non résolu, la décision reste présente et les diagnostics 24B.1 restent visibles.

## 7. Cohérence causale et anti-contamination

Avant de construire le record, le builder vérifie la chaîne d'identité disponible :

```text
opportunity_id
feature_snapshot_id / source_snapshot_id
system_id
symbol
timeframe
observed_at / as_of
DecisionContext id/fingerprint
proposal_id
risk_decision_id
client_order_id
broker_order_id
```

Les artefacts Risk/PAPER actuels ne portent pas tous un `source_backtest_run_id`. Là où le run ID
n'existe pas dans le contrat source, 24B.2 ne l'invente pas : il vérifie la chaîne canonique
`opportunity → proposal → risk → order → fill`. Une contamination avec une autre chaîne qui casse
ces identités est rejetée explicitement.

## 8. Frontière causale avec les outcomes

Le core record contient ce qui était connu ou produit autour de la décision à T :

```text
DecisionIntelligenceRecord
= decision/replay facts + same-as-of Analytics identity
```

Il n'inclut pas :

```text
H1/H3/H5/H10/H20
future return
MFE / MAE futurs
realized P&L futur
closed trade outcome
jugement de qualité
```

Ces données restent dans Batch 23A et pourront être jointes extérieurement lors des recherches
24D.

## 9. Dialogue français

La baseline 24B.2 conserve :

```text
AGENT_DIALOGUE_LANGUAGE = fr-FR
AGENT_DIALOGUE_LANGUAGE_VERSION = money-heist.agent-dialogue.fr.v1
PROMPT_TRANSPORT_VERSION = money-heist.prompt-transport.v4
```

Le builder ne traduit, ne résume et ne régénère aucune sortie agent. Les textes canoniques déjà
émis sont projetés tels quels et les tokens machine restent inchangés.

## 10. Isolation

```text
Decision / Replay artifacts ─────────┐
                                     │
24B.1 OpportunityAnalyticsLink ──────┼──> DecisionIntelligenceRecord
                                     │
Decision Funnel aggregate (optional) ┘    validation only
```

Interdictions :

- Scanner, DecisionContext, Agents, Orchestration, Risk, PAPER et LIVE n'importent pas 24B.2 ;
- `app.analytics` n'importe pas 24B.2 ;
- 24B.1 reste isolé et n'importe pas 24B.2 ;
- 24B.2 n'importe ni Forward Outcomes, ni Analytics Core, ni moteur actif Scanner/Agents/Risk/PAPER ;
- le builder ne déclenche aucun service et n'effectue aucun calcul Analytics ou trading.

## 11. RecordSet

`DecisionIntelligenceRecordSet` contient :

```text
source_backtest_run_id
analytics_run_id
record_count
matched_analytics_count
unmatched_analytics_count
records
set_fingerprint
```

Il exige une couverture exacte 1 `CandidateOpportunity` ↔ 1 link 24B.1 ↔ 1 record.

## 12. Hors scope

24B.2 n'implémente pas :

- 24B.3 Scanner ↔ Analytics Attribution ;
- 24B.4 Funnel Stage ↔ Analytics Attribution ;
- API/UI 24C ;
- rapports de qualité 24D ;
- seuils/tuning automatiques ;
- injection Analytics dans DecisionContext/Scanner/Professor/Risk.
