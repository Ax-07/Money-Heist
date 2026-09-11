# CHANGELOG — Batch 16.16

## LIVE_EVAL cost accounting and Palermo headroom

- Palermo `max_output_tokens` : 2400 → 8192 ;
- ajoute `IncompleteAIProviderError` avec usage facturable ;
- comptabilise et journalise le coût d'une réponse provider incomplète ;
- conserve ces réponses non-retryables automatiquement ;
- conserve hard budget et réservation préalable ;
- aucun changement Risk Engine, PaperBroker ou trading LIVE.
