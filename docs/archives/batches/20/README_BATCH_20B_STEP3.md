# Batch 20b — Step 3 — Composition Closure & Integration Fingerprints

## Goal

Close Batch 20b with an immutable, fail-closed handoff from dynamic composition to the
existing Batch 20a `TaskForcePlan` contract.

This step does **not** execute agents. It does not approve a Task Force, mutate
`AgentRegistry`, call the AI Gateway, invoke the Risk Engine, or touch LIVE execution.

## Added contracts

- `TaskForceCompositionClosureManifest`
- `TaskForceCompositionClosure`
- `task_force_plan_fingerprint(...)`
- `close_task_force_composition(...)`

## Required preconditions

A composition may be closed only when:

- `TaskForceCompositionResult.complete is True`;
- at least one registry-backed member is present;
- the Step 2 audit is `FRESH` and non-stale;
- the audit contains no stale reason codes;
- provenance fingerprints match the current request, operator policy, composition result,
  source bundle, and member set;
- closure time is not before the request;
- closure expiry does not exceed the request expiry.

## Output

The closure builds the existing Batch 20a `TaskForcePlan` in state `PLANNED` and records:

- request fingerprint;
- operator-policy fingerprint;
- Step 2 source-bundle fingerprint;
- Step 1 composition-result fingerprint;
- Batch 20a plan-composition fingerprint;
- exact full-plan fingerprint;
- final integration fingerprint;
- selected member ids;
- attached Batch 18 reputation advisory fingerprints.

The manifest explicitly preserves:

- `operator_authorization_required = True`;
- `execution_authorized = False`;
- `registry_mutation = False`;
- `risk_authority = False`;
- `live_authority = False`.

## Validation

Targeted:

```powershell
uv run pytest -q tests/task_force/test_task_force_composition_closure.py
```

Then full suite:

```powershell
uv run pytest -q
git status --short
```

Do not commit or push until local validation is confirmed.
