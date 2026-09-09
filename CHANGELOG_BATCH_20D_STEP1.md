# Changelog — Batch 20d Step 1

- ajout de `TaskForceTriggerSignal` : besoin explicite, mission, question et audit evidence ;
- ajout de `TaskForceInvocationPolicy` : allowlist de triggers et durée maximale explicites ;
- ajout de `TaskForceInvocationDecision` : `SKIPPED` ou `PROPOSED` ;
- génération déterministe d'un `TaskForceRequest` advisory-only ;
- fingerprint SHA-256 du signal, de la policy et de la décision ;
- UUIDv5 déterministe de la request ;
- validation snapshot/symbole/timeframe/warmup et temporalité anti-look-ahead ;
- aucun seuil de production implicite ;
- aucun appel AI Gateway ;
- aucune mutation AgentRegistry ;
- aucune autorité TradeProposal, Risk, Broker ou LIVE ;
- aucun changement du pipeline d'orchestration principal dans ce step.
