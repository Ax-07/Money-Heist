# Money Heist — Intégration Batch 24B.3

Baseline cible :

```text
repository: Ax-07/Money-Heist
branch: main
commit: 4c0bcdfb4d44421d4282ebaad5232051c0deedfa
```

## Installation

Extraire le ZIP directement à la racine du dépôt :

```text
E:\0 money heist
```

Le ZIP est un overlay : les nouveaux fichiers sont créés et les quelques fichiers existants du batch sont remplacés.

Puis appliquer les addendums documentaires :

```powershell
uv run python .\apply_batch_24b3_docs.py
```

## Validation locale recommandée

```powershell
uv run ruff check `
  app/evaluation/scanner_observations.py `
  app/evaluation/analytics_attribution `
  app/evaluation/scanner_forward_outcomes/models.py `
  tests/evaluation/test_scanner_analytics_attribution.py `
  tests/evaluation/test_scanner_analytics_attribution_architecture.py `
  tests/evaluation/test_opportunity_analytics_attribution.py `
  tests/evaluation/test_scanner_forward_outcomes.py

uv run pytest `
  tests/evaluation/test_opportunity_analytics_attribution.py `
  tests/evaluation/test_scanner_forward_outcomes.py `
  tests/backtest/test_scanner_forward_outcomes.py `
  tests/evaluation/test_decision_intelligence.py `
  tests/evaluation/test_decision_intelligence_architecture.py `
  tests/evaluation/test_analytics_attribution_architecture.py `
  tests/evaluation/test_scanner_analytics_attribution.py `
  tests/evaluation/test_scanner_analytics_attribution_architecture.py `
  -q

uv run pytest tests/analytics -q
```

## Invariants

24B.3 est strictement post-hoc. Il ne modifie ni Scanner, ni Agents, ni Risk, ni PAPER, ni LIVE. `app.analytics` reste observation-only. Le matching exact 24B.1 reste l'unique moteur de résolution Analytics et aucun fallback temporel n'est introduit.
