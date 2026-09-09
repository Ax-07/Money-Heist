# CHANGELOG — Batch 19d Step 1

## Added
- `app/recruitment/advisory.py`
  - évaluation déterministe des success criteria gelés ;
  - actions advisory `REJECT / EXTEND / PROBATION / RECOMMEND_PROMOTION` ;
  - résolution explicite d'un ensemble de métriques Recruitment/Batch 18 ;
  - fail-closed pour métriques indisponibles ou non supportées ;
  - gate OOS stricte pour les critères de promotion ;
  - respect du budget candidat ;
  - fingerprint audit auto-vérifié ;
  - aucune application automatique.
- tests advisory et boundaries dédiés.

## Updated
- `app/recruitment/__init__.py` pour exporter les contrats advisory publics.

## Validation locale de l'overlay cumulatif
- 104 tests Recruitment passent.
- `compileall` passe.
