# Money Heist — Intégration Batch 24B.2

Baseline cible :

```text
repository: Ax-07/Money-Heist
branch: main
commit: 6755266b8e5bd0e8c9d4287914ceb8ee68dec16b
```

Le commit `31bf2ef062ae5a4aa024279cf283d79223103c83` (24B.1) doit être présent dans
l'historique.

## Fichiers du lot

À copier dans le dépôt :

```text
app/evaluation/decision_intelligence/__init__.py
app/evaluation/decision_intelligence/models.py
app/evaluation/decision_intelligence/builder.py
tests/evaluation/test_decision_intelligence.py
tests/evaluation/test_decision_intelligence_architecture.py
docs/BATCH_24B2_DECISION_INTELLIGENCE_RECORD.md
apply_batch_24b2_docs.py
README_BATCH_24B2.md
```

Puis exécuter le script documentaire :

```powershell
uv run python .\apply_batch_24b2_docs.py
```

Ne pas modifier les prompts FR dans ce batch.

Transport FR attendu sur cette baseline :

```text
AGENT_DIALOGUE_LANGUAGE_VERSION=money-heist.agent-dialogue.fr.v1
PROMPT_TRANSPORT_VERSION=money-heist.prompt-transport.v4
```
