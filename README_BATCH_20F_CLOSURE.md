# Batch 20f — Finalisation et clôture

Ce lot ferme **Batch 20 — Task Force dynamique**.

## Contenu

- consolidation des exports publics `app.task_force` ;
- exports lazy Batch 20 dans `app.evaluation` ;
- exports des bridges Task Force dans `app.services.orchestration` ;
- état courant post-Batch 20 ;
- addenda Project Master / Architecture / Agents / Evaluation / Sécurité / API / Replay ;
- roadmap réalignée : Batch 20 livré, Batch 21 prochain ;
- ADR-027 ;
- clôture `CHANGELOG_BATCH.md` ;
- tests de surface publique et de cohérence documentaire.

## Frontières

La clôture ne change aucune logique de trading. Elle ne crée aucune nouvelle autorité Risk/LIVE et
ne modifie pas le comportement du runtime Task Force validé dans 20a–20e.

## Application

```powershell
uv run python apply_batch_20f_closure.py
uv run pytest -q tests/task_force/test_batch20_closure.py
uv run pytest -q
git status --short
```

Le script est idempotent et vérifie les miroirs documentaires avant écriture.
