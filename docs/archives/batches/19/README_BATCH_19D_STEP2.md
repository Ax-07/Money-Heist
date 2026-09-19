# Batch 19d — Step 2 — Advisory Safety Guards & Lifecycle Transition Planning

Baseline attendue : Batch 19d Step 1 installé et validé localement.

## Objectif

Relier un `RecruitmentAdvisoryReport` à un `RecruitmentTransitionPlan` déterministe sans appliquer la transition.

Le planner revalide :

- identité candidat / package / lifecycle / advisory ;
- fingerprint exact du package d'évidence consommé par l'advisory ;
- révision et état lifecycle non périmés ;
- `RecruitmentCandidateSpec` inchangé depuis le gel de l'évidence ;
- politique de capacité et snapshot opérateur explicites ;
- admission SHADOW via le gate Batch 19a ;
- budget opérateur avant progression positive ;
- plafond `max_active_specialists` avant `RECOMMEND_PROMOTION`.

## Mapping advisory → lifecycle

- `REJECT` → `REJECT` ;
- `PROBATION` → `ENTER_PROBATION` ;
- `RECOMMEND_PROMOTION` → `RECOMMEND_PROMOTION` ;
- `EXTEND` depuis `SHADOW` → `EXTEND_SHADOW` ;
- `EXTEND` depuis `PROBATION` → `EXTEND_PROBATION` ;
- `EXTEND` depuis `CANDIDATE` → `ENTER_SHADOW` uniquement si `evaluate_shadow_admission(...)` retourne `ALLOW`.

Un résultat `READY` contient un `RecruitmentTransitionPlan`, mais exige toujours une autorisation opérateur explicite avant `record_recruitment_transition(...)`.

Un résultat `BLOCKED` ne contient aucun `RecruitmentTransitionPlan`.

## Invariants

- `operator_authorization_required = True`
- `auto_apply = False`
- `registry_mutation = False`
- `lifecycle_transition_applied = False`
- `promotion_applied = False`
- `live_authority = False`

Aucun import LIVE, broker LIVE, Risk Engine ou `AgentRegistryEntry` n'est introduit.

## Validation

Après extraction à la racine du dépôt :

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Ne pas committer avant validation des deux suites. Ne pas utiliser `git add -A`.
