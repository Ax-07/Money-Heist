# Batch 19a — Step 2 — Recruitment lifecycle

Baseline attendue : Step 1 installé et validé sur `main` démarrant de `96b2288`.

## Objectif

Ajouter uniquement le cycle de vie déterministe d'un candidat Recruitment, séparé du registre opérationnel.

Le Step 2 apporte :

- un `RecruitmentLifecycleRecord` immuable ;
- une machine d'états explicite ;
- des plans de transition déterministes et fingerprintés ;
- une autorisation opérateur obligatoire avant l'enregistrement d'une transition ;
- une révision monotone empêchant les plans stale ;
- la réversibilité explicite de la recommandation de promotion et du rejet ;
- aucune mutation d'`AgentRegistry` ;
- aucune autorité LIVE.

## Transitions V1

```text
CANDIDATE
  -> SHADOW
  -> REJECTED

SHADOW
  -> SHADOW          (extension)
  -> PROBATION
  -> REJECTED

PROBATION
  -> PROBATION       (extension)
  -> SHADOW
  -> PROMOTION_RECOMMENDED
  -> REJECTED

PROMOTION_RECOMMENDED
  -> PROBATION       (retrait de recommandation)
  -> SHADOW
  -> REJECTED

REJECTED
  -> CANDIDATE       (réouverture opérateur explicite)
```

`PROMOTION_RECOMMENDED` reste une recommandation Recruitment. Ce n'est ni `ACTIVE`, ni `ON_DEMAND`, ni une écriture dans `AgentRegistry`.

## Hors périmètre

Ce step ne décide pas *pourquoi* une transition est méritée. Les gates de population/budget et les preuves Batch 18 arrivent dans les steps suivants. `reason_codes` et `evidence_refs` sont obligatoires uniquement pour garantir l'auditabilité dès maintenant.

## Installation

Extraire le ZIP à la racine du repository après le Step 1.

## Tests

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
```

## Vérification Git

```powershell
git status --short
git diff -- app/recruitment tests/recruitment README_BATCH_19A_STEP2.md CHANGELOG_BATCH_19A_STEP2.md
```

Ne pas utiliser `git add -A`.
