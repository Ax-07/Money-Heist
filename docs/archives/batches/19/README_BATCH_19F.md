# Batch 19f — Closure overlay

Ce lot clôt le Batch 19 sans modifier la logique métier Recruitment.

Après extraction, supprimer les trois doublons racine non suivis :

```powershell
Remove-Item -LiteralPath "01_PROJECT_MASTER.md","02_ARCHITECTURE.md","07_SECURITE_ET_OPERATIONS.md" -Force
```

Puis exécuter :

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Ne pas commit/push avant validation complète. Ne pas utiliser `git add -A`.
