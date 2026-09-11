# CHANGELOG — Batch 16.15

## LIVE_EVAL robustness

- accepte `list[0].field` comme équivalent strict de `list.0.field` pour le grounding ;
- conserve le rejet fail-closed des chemins invalides ou inexistants ;
- ajoute un plafond de sortie ciblé de 2400 tokens pour Palermo ;
- laisse les plafonds des autres agents inchangés ;
- conserve la réservation et le hard budget du gateway ;
- aucun changement Risk Engine, PaperBroker ou trading LIVE.
