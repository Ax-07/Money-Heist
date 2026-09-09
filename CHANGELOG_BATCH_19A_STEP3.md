# Changelog — Batch 19a Step 3

## Ajouté

- politique de capacité Recruitment explicitement fournie par l'opérateur ;
- snapshot read-only population/fréquence par période ;
- gate déterministe d'admission `CANDIDATE → éligible SHADOW` ;
- gate déterministe de budget compute par candidat ;
- reason codes auditables ;
- fingerprints SHA-256 déterministes ;
- tests ciblés et tests statiques de frontières.

## Invariants préservés

- aucune valeur de seuil de production inventée ;
- aucune mutation automatique de `AgentRegistry` ;
- aucune transition lifecycle automatique ;
- aucune autorité LIVE ;
- aucune dépendance Risk Engine / broker LIVE ;
- aucun scoring Recruitment parallèle au Batch 18.
