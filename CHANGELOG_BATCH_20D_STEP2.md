# CHANGELOG — Batch 20d Step 2

## Added

- Validation déterministe d'un `TaskForceReport` avant consommation par l'orchestration.
- Recalcul du fingerprint Batch 20c du rapport.
- Payload advisory `task_force_report` pour la finalisation du Professor.
- Grounding explicite sur `task_force_report.*` quand le rapport est présent.
- Audit event `task_force_report` dans le pipeline.
- Tests de validation du bridge et tests d'intégration post-apply.
- Apply script idempotent pour modifier uniquement les deux fichiers suivis nécessaires.

## Unchanged

- Palermo et son contrat `PalermoReview`.
- Specialist round 1.
- Compute Gate historique.
- `TradeProposal` et sa frontière avec le Risk Engine.
- PaperBroker / LiveBroker / LIVE gates.
- AgentRegistry et états d'agents.
