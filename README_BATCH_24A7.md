# Money Heist — Batch 24A.7 root-extract package

Baseline attendue : `0dc8200025ae7ca43964cadc04dff6e1ba1ac065`.

Ce ZIP est conçu pour être **extrait directement à la racine du dépôt Money-Heist**.
Il contient directement `app/`, `tests/`, `docs/` et le script documentaire à la racine ; il n'y a aucun dossier `payload/` ou `overlay/` intermédiaire.

Après extraction depuis la racine du dépôt :

```powershell
git rev-parse HEAD
uv run python .\apply_batch_24a7_docs.py
uv run ruff check app/analytics/research tests/analytics/research apply_batch_24a7_docs.py
uv run pytest tests/analytics/research -q
uv run pytest tests/analytics -q
uv run pytest -q
git status --short
git diff --stat
```

Ne pas committer avant validation complète.

## Component manifest integration

Batch 24A.7 exposes `causal_research_component_versions()` with bundle version
`analytics-lab-24a7-contexts-sequences-v1`. The manifest carries the installed
context and sequence resolver versions instead of `not-installed`.
