# Batch 17a — Finalisation — MOCK avancé et documentation

## Pré-requis

Ce ZIP s'applique par-dessus **Batch 17a Step 1 + Step 2**, déjà validés localement.

## Objectif

Finaliser Batch 17a sans ajouter de nouvelle capacité de trading : rendre Rio/Denver testables en
MOCK de manière déterministe, préserver strictement le comportement historique lorsque les agents
avancés ne sont pas disponibles, et réaligner la documentation active.

## Contenu code

- `DeterministicAdvancedSpecialistMockProvider` : wrapper du provider MOCK existant ;
- tous les schémas legacy sont délégués au fallback sans modification ;
- `ProfessorPlan` n'est modifié que si `denver` ou `rio` figure réellement dans
  `available_agents` ;
- Denver MOCK reste `NEUTRAL` sur la direction et interprète seulement les statistiques fournies ;
- Rio MOCK reste `NEUTRAL` et ne fabrique aucun sentiment externe ;
- absence de `stats_id`, `sample_size_band` ou `data_quality` grounded = échec explicite ;
- aucun accès broker, Risk Engine, LIVE, portefeuille, secret ou sizing.

## Garanties de non-régression

Sans contexte avancé, le wrapper retourne la réponse du provider legacy telle quelle. Cela garantit
que les backtests MOCK existants qui ne sélectionnent ni Rio ni Denver conservent le même plan et la
même réponse fournisseur.

## Documentation mise à jour

- état actuel ;
- système d'agents ;
- market data ;
- évaluation ;
- API/modèles ;
- roadmap ;
- décisions/changelog ;
- contrat backtest.

Le Batch 17a est séparé du futur **Batch 17b — Rio avec vraies données dérivées**.

## Validation recommandée

```powershell
uv run pytest -q tests/backtest/test_advanced_mock.py tests/backtest/test_setup_stats.py tests/orchestration/test_advanced_specialists.py

uv run ruff check `
  app/services/backtest/__init__.py `
  app/services/backtest/advanced_mock.py `
  app/services/backtest/setup_stats.py `
  app/services/orchestration/specialist_contexts.py `
  app/services/orchestration/pipeline.py `
  tests/backtest/test_advanced_mock.py `
  tests/backtest/test_setup_stats.py `
  tests/orchestration/test_advanced_specialists.py `
  --output-format concise

uv run pytest -qq --disable-warnings
```

Le `ruff check .` global reste hors critère de ce batch à cause de la dette Ruff historique déjà
identifiée hors périmètre Batch 17a.
