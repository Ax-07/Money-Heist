# Batch 16.17 — Palermo targeted timeout

## Constat LIVE_EVAL

Le run `40628b2a-9510-4ce0-a01d-309c5d16bb8d` confirme :

- 0 `UNGROUNDED_EVIDENCE` ;
- 0 `incomplete:max_output_tokens` ;
- 2 `AI_PROVIDER_ERROR` au stage `palermo_red_team` ;
- message : `OpenAI transport failure:`.

La route `core_reasoning` utilise un timeout générique de 30 secondes.
Palermo peut désormais produire jusqu'à 8192 tokens ; il reçoit donc une
fenêtre réseau plus large sans ralentir tous les autres agents.

## Correctif

- ajoute un override de timeout optionnel à `AIGatewayRequest` ;
- Palermo utilise 90 secondes ;
- Professor, Lisbon et spécialistes conservent le timeout de route de 30 s ;
- le `ProviderRequest` sélectionne l'override seulement lorsqu'il est fourni ;
- les erreurs transport incluent désormais le type d'exception (`ReadTimeout`,
  `ConnectError`, etc.) même lorsque le message natif est vide.

## Invariants

- `max_output_tokens` Palermo reste 8192 ;
- hard budget inchangé ;
- retry policy inchangée ;
- Risk Engine inchangé ;
- PaperBroker inchangé ;
- aucun trading LIVE.

## Validation

```powershell
uv run pytest -q tests/intelligence/test_ai_gateway_timeout.py
uv run pytest -q tests/intelligence/test_openai_responses_client.py
uv run pytest -q tests/agents/test_core_agents.py
uv run pytest -q
```
