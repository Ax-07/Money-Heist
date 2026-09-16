# Money Heist — Intégration Batch 24A.1

Baseline GitHub auditée :

```text
Ax-07/Money-Heist
main
55a5333941ffc043b26b5e30f4b9fdafbd1cf8b0
```

Le lot ajoute uniquement la fondation observation-only de l'Analytics Lab, ses
contrats, son adaptateur Historical Replay et ses tests. Il ne modifie aucun
contrat Scanner, CandidateOpportunity, DecisionContextV1, agents, Risk, PAPER ou
LIVE.

## Application

Extraire le ZIP à la racine du dépôt Money Heist en conservant l'arborescence et
en autorisant le remplacement de `app/services/backtest/ids.py`.

Puis exécuter :

```powershell
cd "E:\0 money heist"

git rev-parse HEAD
git status --short

uv run python apply_batch_24a1_docs.py
uv sync

uv run pytest -q tests/analytics
uv run pytest -q tests/backtest/test_reproducibility.py tests/backtest/test_exports.py
uv run pytest -q tests/market/test_multitimeframe_cursor.py tests/services/decision_context/test_decision_context_models.py
uv run pytest -q

uv run ruff check app tests apply_batch_24a1_docs.py
uv run ruff format --check app tests apply_batch_24a1_docs.py

git diff --check
git status --short
git diff --stat
git diff -- app/services/backtest/ids.py
```

La première commande `git rev-parse HEAD` doit afficher la baseline ci-dessus si
aucun commit local n'a été ajouté entre-temps. Si le HEAD local est différent,
ne pas committer le batch avant audit du delta.

## Pourquoi `app.common.canonical` existe

`app.services.backtest.ids` contenait déjà la canonicalisation Money Heist, mais
importer ce sous-module depuis Analytics déclenche d'abord
`app.services.backtest.__init__`, lequel expose également les composants post-hoc
Batch 23A. Pour conserver une frontière Analytics stricte, la primitive est
factorisée à l'identique dans `app.common.canonical` et l'API historique
`app.services.backtest.ids` la ré-exporte.

`tests/analytics/test_canonical_contract.py` verrouille un golden JSON, SHA-256
et UUID5 afin de détecter toute dérive des fingerprints historiques.

## Documentation

`apply_batch_24a1_docs.py` est idempotent. Il ajoute les sections 24A.1 aux
documents canoniques existants sans les remplacer, ainsi qu'une entrée au
`CHANGELOG_BATCH.md`. Le script échoue si un document canonique attendu manque.

## Clôture

Ne pas pousser ni committer avant validation locale complète. Après les commandes
ci-dessus, transmettre les sorties de `pytest`, `ruff`, `git status`,
`git diff --check` et `git diff --stat` pour revue finale.
