# Batch 16.16 — Billable incomplete responses

## Constat LIVE_EVAL

Après le Batch 16.15 :

- le grounding final est propre : 0 `UNGROUNDED_EVIDENCE` ;
- Palermo atteint encore `max_output_tokens` sur certaines opportunités ;
- le client OpenAI levait l'erreur avant d'extraire l'usage, ce qui faisait
  libérer la réservation du gateway comme si l'appel incomplet n'avait rien coûté.

Une réponse `incomplete:max_output_tokens` peut pourtant avoir consommé des
tokens facturables.

## Correctif

- Palermo passe de 2400 à 8192 `max_output_tokens` ;
- `incomplete:max_output_tokens` reste non-retryable automatiquement ;
- l'usage retourné par le provider est attaché à l'erreur ;
- le gateway solde la réservation au coût réel avant de remonter l'erreur ;
- un `AIUsageRecord` est enregistré pour l'appel incomplet ;
- aucun retry automatique ni double dépense cachée n'est ajouté.

## Sécurité

- hard budget inchangé ;
- réservation préalable inchangée ;
- Risk Engine inchangé ;
- PaperBroker inchangé ;
- aucun trading LIVE.

## Validation

```powershell
uv run pytest -q tests/intelligence/test_openai_responses_client.py
uv run pytest -q tests/intelligence/test_ai_gateway_budget.py
uv run pytest -q tests/agents/test_core_agents.py
uv run pytest -q
```
