# Batch 16.15 — LIVE_EVAL robustness

## Incidents observés

Le smoke LIVE_EVAL termine 345/345 mais trois opportunités échouent techniquement :

- 2 × Palermo : `OpenAI response incomplete: max_output_tokens`
- 1 × Professor : `specialist_analyses[0].multi_timeframe_alignment`

## Correctif grounding

Le validateur accepte désormais la notation numérique `list[0].field` comme
équivalent strict de `list.0.field`.

Seuls les index numériques sont normalisés. Les chemins inexistants,
hors plage, négatifs ou non numériques restent rejetés fail-closed.

## Correctif Palermo

Palermo reçoit un override ciblé :

- Palermo : `max_output_tokens = 2400`
- Professor : inchangé
- spécialistes : inchangés
- Lisbon : inchangé
- budget dur campagne : inchangé

Le gateway continue de réserver le coût maximum avant l'appel et de solder le
coût réel après l'appel.

## Sécurité

Aucun changement du Risk Engine, PaperBroker ou trading LIVE.

## Validation

```powershell
uv run pytest -q tests/orchestration/test_final_evidence_grounding.py
uv run pytest -q tests/agents/test_core_agents.py
uv run pytest -q
```
