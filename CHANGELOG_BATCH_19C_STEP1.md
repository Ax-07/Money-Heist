# Changelog — Batch 19c Step 1

## Ajouté

- `app/recruitment/ablation_bridge.py`
  - `RecruitmentAblationSemantics`
  - `RecruitmentAblationBridgeResult`
  - `bridge_recruitment_to_ablation(...)`
- exports publics Recruitment associés ;
- tests de mapping sémantique vers Batch 18 ;
- tests de refus gate BLOCK/stale ;
- tests de boundary contre imports Registry/Risk/LIVE ;
- audit fingerprint déterministe du bridge.

## Invariants

- réutilisation de `app.evaluation.ablation.compare_ablation` ;
- aucun nouveau moteur de métriques marginales ;
- `WITH_CANDIDATE` est le système complet Batch 18 ;
- Recruitment `BASELINE` est le twin sans candidat ;
- aucune mutation AgentRegistry ;
- aucune action de promotion ;
- aucun accès LIVE ;
- aucun changement Risk Engine.
