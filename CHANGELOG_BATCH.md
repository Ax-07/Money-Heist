# CHANGELOG — Batch 08 — Orchestration complète

## Ajouté

- `app/services/orchestration/compute_gate.py`
  - Compute Gate déterministe avant les appels IA ;
  - niveaux `SKIP_AI`, `LEVEL_2_MINI_CREW`, `LEVEL_3_FULL_CREW` ;
  - contrôle priorité, expiration et budget restant ;
  - seuils de préflight configurables sans modifier le plafond dur du ledger.

- `app/services/orchestration/models.py`
  - décision finale stricte du Professor ;
  - paramètres de trade structurés ;
  - `TradeProposal` Batch 08 ;
  - statuts/failures du pipeline ;
  - audit des appels agents et des étapes ;
  - conservation des IDs d’opportunité, snapshot et requêtes IA.

- `app/services/orchestration/pipeline.py`
  - pipeline `CandidateOpportunity -> Compute Gate -> Professor -> spécialistes -> Palermo -> Professor -> TradeProposal` ;
  - sélection dynamique Berlin/Tokyo/Nairobi ;
  - premier tour réellement indépendant et lancé en concurrence ;
  - Palermo uniquement après la fin du tour indépendant ;
  - arrêt sûr sur sortie invalide, preuve non fondée ou budget insuffisant ;
  - `NO_ANALYSIS` et `NO_TRADE` comme sorties de premier niveau ;
  - aucune connexion au Paper Broker, à un exchange ou au Risk Engine.

## Adaptation rétrocompatible

- `app/agents/core.py`
  - ajout de `TheProfessor.finalize_with_schema(...)` pour permettre au Batch 08 d’imposer un schéma final plus strict ;
  - `TheProfessor.finalize(...)` conserve son contrat et son comportement existants en déléguant au nouveau helper.

## Sécurité / intégrité

- Les champs `None` du `FeatureSnapshot` sont exclus du payload agentique afin qu’une donnée manquante ne puisse pas être citée comme preuve disponible.
- Les références de preuves spécialistes restent contrôlées par les garde-fous du Batch 07b.
- Les preuves de la décision finale du Professor sont elles aussi validées contre les entrées réellement transmises.
- Le Compute Gate ne remplace pas le ledger : l’AI Gateway conserve l’autorité dure sur chaque réservation et chaque dépense.
- Aucun secret, broker, exchange, shell, filesystem arbitraire ou Risk Engine n’est exposé aux agents.

## Tests ajoutés

Couverture notamment :
- pipeline nominal ;
- Compute Gate mini/full/skip ;
- `NO_ANALYSIS` ;
- `NO_TRADE` ;
- sélection des spécialistes ;
- indépendance, concurrence réelle et absence de contamination du premier tour ;
- ordre spécialistes -> Palermo ;
- sortie `TradeProposal` structurée ;
- audit et rattachement des IDs ;
- respect du budget / budget insuffisant / plafond dur ;
- sortie spécialiste invalide ;
- sortie Palermo invalide ;
- sortie Professor invalide ;
- preuve finale du Professor non fondée ;
- preuve inexistante ou champ manquant ;
- snapshot incohérent ;
- absence de dépendance broker/exchange/secrets/Risk Engine.

## Dépendances

Aucune nouvelle dépendance.
