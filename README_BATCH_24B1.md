# Money Heist — Intégration Batch 24B.1

Ce lot cible exclusivement la baseline :

```text
6d67e3f25a6c95f23552a5f4f025bd1b4d29a26c
```

Il ne pousse rien vers GitHub et ne modifie aucun chemin trading.

## Fichiers nouveaux

```text
app/evaluation/analytics_attribution/__init__.py
app/evaluation/analytics_attribution/models.py
app/evaluation/analytics_attribution/index.py
app/evaluation/analytics_attribution/linker.py

tests/evaluation/test_opportunity_analytics_attribution.py
tests/evaluation/test_analytics_attribution_architecture.py

docs/BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING.md
apply_batch_24b1_docs.py
README_BATCH_24B1.md
```

Les documents permanents et `CHANGELOG_BATCH.md` sont mis à jour par le script idempotent
`apply_batch_24b1_docs.py` après contrôle du HEAD.

## Commandes d'intégration et validation

Depuis `E:\0 money heist` après copie/extraction du lot :

```powershell
git rev-parse HEAD
git status --short

uv run python .\apply_batch_24b1_docs.py

uv run ruff check `
  app/evaluation/analytics_attribution `
  tests/evaluation/test_opportunity_analytics_attribution.py `
  tests/evaluation/test_analytics_attribution_architecture.py `
  apply_batch_24b1_docs.py

uv run pytest tests/evaluation/test_opportunity_analytics_attribution.py -q
uv run pytest tests/evaluation/test_analytics_attribution_architecture.py -q
uv run pytest tests/analytics -q
uv run pytest tests/backtest/test_reproducibility.py -q
uv run pytest tests/evaluation -q
uv run pytest -q

git status --short
git diff --stat
git diff
```

Le `git rev-parse HEAD` initial doit être exactement :

```text
6d67e3f25a6c95f23552a5f4f025bd1b4d29a26c
```

Ne pas committer avant analyse des sorties de validation.

## Critères de clôture

Le batch ne doit être considéré clos qu'après :
- Ruff PASS ;
- tests 24B.1 PASS ;
- `tests/analytics` PASS ;
- test reproductibilité PASS ;
- suites Evaluation/Backtest concernées PASS ;
- full suite PASS avec uniquement les skips attendus ;
- working tree audité sans fichier temporaire ;
- confirmation que le business fingerprint n'a pas changé.
