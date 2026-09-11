# Batch 16.12 — OpenAI Structured Outputs schema compatibility

## Incident observé

Le premier replay `LIVE_EVAL` atteint correctement l'API OpenAI et obtient des
sorties structurées valides pour :

- Professor PLAN ;
- Berlin ;
- Tokyo ;
- Palermo.

L'échec arrive ensuite à `professor_finalize` avec :

```text
OpenAI HTTP 400: Invalid JSON schema: regex lookaround is not supported.
Found at $['$defs'].ProfessorTradeParameters.properties.entry_price.anyOf[1].pattern.
```

## Cause

Pydantic représente un `Decimal` en JSON Schema comme une union :

- `number` ;
- ou `string` avec une regex de compatibilité.

La regex générée contient un negative lookahead `(?!...)`. Le dialecte de
Structured Outputs utilisé par l'API OpenAI refuse ce lookaround.

## Correctif

Le modèle métier reste strictement en `Decimal`.

Seul le schéma **envoyé au provider** est normalisé par
`build_strict_json_schema()` :

- lorsqu'une union Pydantic contient une branche `number` et une branche
  `string` dont la regex utilise un lookaround non supporté, la branche string
  de compatibilité est retirée ;
- le JSON demandé au provider doit alors utiliser un vrai `number` ;
- Pydantic continue de valider la réponse dans le modèle `Decimal` métier ;
- un lookaround restant dans un autre champ provoque désormais une
  `AIConfigurationError` locale, avant tout appel provider.

Aucun changement du Risk Engine, PaperBroker, orchestration métier,
`ProfessorTradeParameters`, ni des règles PAPER/LIVE.

## Installation

Extraire le ZIP à la racine du repo puis :

```powershell
uv run python apply_batch_16_12_openai_schema_compat.py
uv run pytest -q tests/intelligence/test_strict_schema.py
uv run pytest -q
```

Ne relancer `LIVE_EVAL` qu'après ces deux suites vertes.
