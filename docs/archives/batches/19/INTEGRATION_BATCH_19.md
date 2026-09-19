# Intégration — Batch 19 — Recruitment Engine

## Prérequis

Baseline d’entrée : Batch 18 complet (`96b2288`).

Les overlays 19a à 19e doivent déjà être extraits et validés avant la clôture 19f.

## Nettoyage documentaire obligatoire

Le Step 19e.2 a créé trois copies racine qui ne font pas partie du layout Git historique. Après extraction du ZIP 19f, supprimer :

```powershell
Remove-Item -LiteralPath "01_PROJECT_MASTER.md","02_ARCHITECTURE.md","07_SECURITE_ET_OPERATIONS.md" -Force
```

Les copies canoniques restent sous `docs/`.

## Validation

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Ne pas utiliser `git add -A`.

Le commit doit être préparé uniquement après validation locale complète et avec un staging explicite du périmètre Batch 19.
