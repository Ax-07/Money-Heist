# Changelog — Batch 19b Step 1

## Ajouté

- plan déterministe `BASELINE` / `WITH_CANDIDATE` ;
- identité runtime d'évaluation séparée d'`AgentRegistry` ;
- réutilisation des contrats Batch 16 `BacktestRun` / `BacktestConfig` / `BacktestPeriodRole` ;
- fingerprints de campagne/comparaison/critères ;
- réservation explicite des métadonnées Recruitment dans les hypothèses du run ;
- tests de déterminisme, comparabilité et frontières anti-LIVE/anti-registry.

## Non ajouté

- aucune exécution de campagne ;
- aucun scoring Recruitment ;
- aucune décision de recrutement ;
- aucune mutation `AgentRegistry` ;
- aucun changement Risk Engine ;
- aucune capacité LIVE.
