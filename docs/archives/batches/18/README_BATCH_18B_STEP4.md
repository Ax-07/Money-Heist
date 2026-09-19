# Money Heist — Batch 18b Step 4 — Clôture Batch 18

## Objectif

Fermer Batch 18 après validation des Steps 18a et 18b.1–18b.3.

Ce lot :

- expose les contrats de campagne via des exports lazy pour éviter les cycles d'import ;
- expose le PAPER Runtime Factory depuis `app.services.backtest` sans import eager ;
- ajoute un export compact `dict/json` du rapport de campagne ;
- supprime le tombstone de migration Step 3 ;
- ajoute les addenda Evaluation / API / Roadmap / Backtesting / Changelog ;
- conserve Evaluation sans import du Risk Engine ;
- ne modifie ni AgentRegistry, ni règles Risk, ni broker LIVE.

## Installation

Extraire le ZIP à la racine du dépôt après le Step 3 architecture fix.

Puis exécuter :

```powershell
uv run python apply_batch_18b_step4_closure.py
```

Le script est idempotent pour la documentation et supprime
`app/evaluation/ablation_campaign_runtime.py` s'il existe encore.

## Validation ciblée

```powershell
uv run pytest -q `
  tests/evaluation/test_ablation_campaign_exports.py `
  tests/evaluation/test_batch18b_public_api.py `
  tests/evaluation/test_batch18b_closure.py `
  tests/evaluation/test_boundaries.py
```

## Validation complète

```powershell
uv run pytest -q
```

## Frontières finales

Batch 18 fournit une infrastructure de preuve. Il ne transforme pas une ablation en preuve causale
universelle, ne fixe pas les seuils opérateur, ne change pas automatiquement l'état d'un agent et
n'autorise jamais le trading LIVE.
