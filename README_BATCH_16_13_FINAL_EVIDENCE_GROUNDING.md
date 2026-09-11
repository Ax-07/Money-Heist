# Batch 16.13 — Final evidence grounding paths

## Incident LIVE_EVAL

Le smoke LIVE_EVAL Batch 16.12 termine le replay, mais 6 opportunités
échouent à `professor_finalize` avec `UNGROUNDED_EVIDENCE`.

Les deux formes observées sont notamment :

- `palermo_review.critical_objections` / `palermo_review.missing_checks` ;
- `tokyo.breakout_quality`.

## Cause

Le validateur final n'acceptait que les feuilles JSON. Une liste réellement
fournie comme `palermo_review.critical_objections` était donc rejetée même si
le chemin existe.

Les analyses spécialistes sont transportées comme une liste
`specialist_analyses`, alors que le Professor les identifie naturellement par
leur `agent`, par exemple `tokyo.breakout_quality`.

## Correctif

- tous les chemins JSON réellement présents, y compris objets/listes
  conteneurs, deviennent citables ;
- un alias déterministe `<agent>.<field>` est accepté uniquement si une analyse
  réellement fournie déclare cet agent ;
- un alias ambigu (deux analyses portant le même `agent`) est supprimé et
  échoue fail-closed ;
- les chemins inexistants restent rejetés.

Aucune modification du Risk Engine, du PaperBroker, du broker LIVE, du budget
IA ou des règles de trading.

## Validation

```powershell
uv run pytest -q tests/orchestration/test_final_evidence_grounding.py
uv run pytest -q
```

Ne relancer LIVE_EVAL qu'après commit/push et mise à jour de `Code version`.
