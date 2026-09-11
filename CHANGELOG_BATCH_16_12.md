# CHANGELOG — Batch 16.12

## OpenAI Structured Outputs schema compatibility

- corrige l'incompatibilité entre les regex Decimal générées par Pydantic et
  le dialecte JSON Schema strict de l'API OpenAI ;
- conserve `Decimal` dans tous les modèles métier ;
- normalise uniquement le schéma provider en préférant la branche JSON
  `number` ;
- ajoute une détection locale des regex lookaround non supportées ;
- ajoute des tests de non-régression sur `ProfessorFinalDecision` et tous les
  modèles de sortie du gateway ;
- aucun changement du Risk Engine, PaperBroker ou trading LIVE.
