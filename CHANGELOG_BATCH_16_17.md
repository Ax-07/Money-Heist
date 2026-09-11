# CHANGELOG — Batch 16.17

## Palermo targeted transport timeout

- ajoute `AIGatewayRequest.timeout_seconds` optionnel ;
- Palermo : timeout 90 s ;
- autres agents : timeout de route inchangé à 30 s ;
- améliore le diagnostic des erreurs transport OpenAI ;
- ne modifie ni budget, ni retry policy, ni Risk Engine, ni PaperBroker.
