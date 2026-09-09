# Changelog — Batch 20e Step 1

## Added

- `TaskForceRunOutcome` pour décrire des runs comparables baseline/treatment.
- `compare_task_force_outcomes()` avec validation stricte de comparabilité et conventions de
  signe explicites.
- `TaskForceEvaluationReport` multidimensionnel et advisory-only.
- `evaluate_task_force()` pour coûts, attempts, latence, taille, Red Team et métriques
  économiques optionnelles.
- Fingerprint SHA-256 déterministe du rapport d'évaluation.
- 13 tests ciblés couvrant coût, provenance, comparabilité, stale evidence et frontières
  d'autorité.
