# Batch 16.20 — Gate-Aware Planning & Palermo Headroom

## Constat LIVE_EVAL

Campagne : `276d3463-cec7-44e4-9022-b7abfba3a2df`

Résultats utiles :
- 345/345 ;
- 15 opportunités ;
- 2 décisions finales SHORT ont atteint le Risk Engine ;
- 1 proposition RESIZED puis exécutée en PAPER ;
- 1 proposition REJECTED par le Risk Engine pour MIN_NOTIONAL.

Échecs techniques restants :
1. deux `INVALID_PROFESSOR_PLAN` : le Professor a demandé `FULL_CREW` alors que le
   Compute Gate n'autorisait que `LEVEL_2_MINI_CREW` ;
2. un `AI_PROVIDER_ERROR` Palermo : `incomplete:max_output_tokens`.

## Cause

Le validateur fail-closed connaît le niveau du Compute Gate, mais `TheProfessor.plan()`
ne recevait pas explicitement cette enveloppe. Le Professor pouvait donc demander
`FULL_CREW` sans savoir que le gate limitait la campagne à `MINI_CREW`.

Palermo dispose déjà d'un timeout ciblé de 90 s et de 8192 tokens de sortie, mais
un cas réel a encore atteint `max_output_tokens`.

## Correctif

- conserve `professor@v1` et `professor@v2` ;
- ajoute et active `professor@v3` ;
- transmet au PLAN une enveloppe déterministe `planning_constraints` :
  - `compute_gate_level` ;
  - `allowed_decisions` ;
  - `max_specialists` ;
  - `full_crew_allowed` ;
- conserve `_validate_plan()` inchangé et fail-closed ;
- Palermo reste `palermo@v2` ;
- augmente uniquement `PALERMO_MAX_OUTPUT_TOKENS` de 8192 à 16384 ;
- timeout Palermo reste 90 s.

## Invariants

- aucun assouplissement du Compute Gate ;
- aucun changement Scanner ;
- aucun changement Feature Engine ;
- aucun changement spécialistes ;
- aucun seuil Risk Engine modifié ;
- Risk Engine déterministe inchangé ;
- PaperBroker inchangé ;
- aucun trading LIVE ;
- aucun trade forcé.

## Validation

```powershell
uv run pytest -q tests/agents/test_core_agents.py
uv run pytest -q tests/orchestration/test_pipeline.py
uv run pytest -q
```
