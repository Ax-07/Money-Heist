# Batch 20d — Step 1 — Task Force Trigger Bridge

## Objectif

Ajouter le contrat d'invocation entre l'orchestration existante et les Task Forces sans modifier
le pipeline principal dans ce step.

Le bridge transforme uniquement un **signal explicite** en proposition `TaskForceRequest` lorsque
le trigger est autorisé par une politique opérateur explicite.

Aucun seuil de production n'est déduit depuis `priority_score`, le régime de marché ou une autre
métrique. La détection métier du besoin reste en amont et doit produire un
`TaskForceTriggerSignal` explicite et auditable.

## Flux

```text
CandidateOpportunity + FeatureSnapshot
+ TaskForceTriggerSignal explicite
+ TaskForceInvocationPolicy opérateur
        ↓
validation contexte / temporalité / warmup
        ↓
trigger enabled ?
  non → SKIPPED
  oui → TaskForceRequest PROPOSED
```

Une proposition n'est jamais une autorisation d'exécution :

```text
execute_task_force = False
operator_authorization_required = True
trade_proposal_authority = False
registry_mutation = False
risk_authority = False
live_authority = False
```

## Invariants

- snapshot, symbole et timeframe doivent correspondre à l'opportunité ;
- le FeatureSnapshot ne peut pas provenir du futur par rapport au signal ;
- l'opportunité ne peut pas être expirée ;
- la durée de vie de la request est bornée par la policy et par `opportunity.expires_at` ;
- rôles, capabilities et besoin Red Team sont conservés tels que fournis, jamais inférés ;
- signal, policy, decision et request sont fingerprintés de manière déterministe ;
- le bridge n'appelle aucun agent, AI Gateway, Risk Engine ou broker ;
- le pipeline principal n'est pas encore modifié dans ce step.

## Validation préparatoire

Harness ciblé : `12 passed`.

Harness cumulatif Task Force + bridge, avec support pytest-asyncio explicitement désactivé :
`116 passed`.

## Validation locale attendue

```powershell
uv run pytest -q tests/orchestration/test_task_force_trigger.py
uv run pytest -q
git status --short
```
