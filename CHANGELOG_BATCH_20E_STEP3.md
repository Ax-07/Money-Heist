# CHANGELOG — Batch 20e Step 3

Ajout de `app/evaluation/task_force_replay_audit.py` :

- `TaskForceReplaySeal` immutable ;
- `TaskForceReplayAudit` avec statuts `FRESH` / `STALE` ;
- fingerprints déterministes du plan, de la campagne, de la comparaison et de l'évaluation ;
- recomputation du fingerprint replay Step 2 ;
- contrôle du fingerprint `TaskForceReport` ;
- détection explicite des dérives baseline/treatment/business/evaluation/comparison ;
- `assert_task_force_replay_fresh()` fail-closed ;
- aucune nouvelle autorité opérationnelle.

Ajout de 15 tests ciblés.
