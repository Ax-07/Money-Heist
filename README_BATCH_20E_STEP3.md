# Batch 20e — Step 3 — Replay Seal & Stale Guards

Ce Step clôt le Batch 20e en ajoutant un seal immutable et un audit déterministe aux campagnes historiques Task Force.

## Objectif

Sceller les preuves reproductibles d'une campagne `BASELINE` / `WITH_TASK_FORCE` et détecter toute dérive avant réutilisation :

- plan de replay complet ;
- fingerprint de campagne ;
- business fingerprints baseline / treatment ;
- `TaskForceReport` ;
- comparaison d'outcomes ;
- évaluation Task Force ;
- fingerprint replay Batch 20e Step 2.

Les objets runtime transitoires (`replay_result`, `evaluation_bundle`) ne font volontairement pas partie du seal.

## Statuts

- `FRESH` : toutes les preuves correspondent au seal ;
- `STALE` : au moins une dérive est détectée avec des reason codes explicites.

`assert_task_force_replay_fresh()` lève `PermissionError` si l'audit est stale.

## Frontières

Le seal et l'audit restent :

- PAPER-only ;
- advisory-only ;
- sans exécution automatique ;
- sans mutation de registry ;
- sans autorité TradeProposal, Risk ou LIVE.

## Validation

```powershell
uv run pytest -q tests/evaluation/test_task_force_replay_audit.py
uv run pytest -q
git status --short
```
