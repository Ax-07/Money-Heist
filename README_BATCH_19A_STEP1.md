# Batch 19a — Step 1 — Recruitment contracts

Baseline attendue : `main` au commit `96b2288` (`feat(evaluation): complete Batch 18 reputation and ablation`).

## Objectif

Introduire uniquement les contrats immuables du Recruitment Engine :

- proposition de recrutement auditable ;
- spécification du candidat ;
- baseline prédéfinie ;
- critères de succès prédéfinis et OOS ;
- budget candidat explicite ;
- état de candidature séparé de `AgentState` / `AgentRegistryEntry` ;
- aucune autorité LIVE, aucun auto-register, aucune auto-promotion.

Ce step ne lance aucune campagne, ne calcule aucune réputation et ne prend aucune décision de recrutement.

## Installation

Extraire le ZIP à la racine du repository.

## Tests

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
```

## Vérification Git avant commit

```powershell
git status --short
git diff -- app/recruitment tests/recruitment README_BATCH_19A_STEP1.md CHANGELOG_BATCH_19A_STEP1.md
```

Ne pas utiliser `git add -A`.
