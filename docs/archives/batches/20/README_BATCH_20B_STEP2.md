# Batch 20b — Step 2 — Composition Audit & Stale Detection

This overlay adds deterministic provenance and stale detection around Batch 20b Step 1
Task Force composition.

## Added

- `app/task_force/composition_audit.py`
  - content-addressed source provenance;
  - fingerprints for composition policy, full AgentRegistry, capability profiles and
    Batch 18 reputation evidence;
  - reproducibility check when provenance is captured;
  - recomposition-based stale audit;
  - explicit reason codes for source changes;
  - no execution, registry, Risk Engine or LIVE authority.
- `tests/task_force/test_task_force_composition_audit.py`
  - fresh reproduction;
  - material request/policy changes;
  - registry contract drift, including unselected agents;
  - capability and reputation drift;
  - order-independent source fingerprints;
  - provenance/result binding rejection;
  - authority invariants.
- `app/task_force/__init__.py`
  - exports for the new audit/provenance contracts.

## Stale semantics

A captured composition becomes stale if any material source changes:

- Task Force request;
- Task Force operator policy;
- composition policy;
- AgentRegistry contents/contracts;
- capability profiles;
- Batch 18 reputation evidence;
- or the deterministic recomposed result.

The audit fingerprints the complete registry, not only selected members. This is deliberate:
an unselected agent can become relevant after a registry change and alter deterministic selection.

`FRESH` does not authorize execution. The audit object always keeps
`execution_authorized=False`, `registry_mutation=False`, `risk_authority=False` and
`live_authority=False`.

## Local validation

```powershell
uv run pytest -q tests/task_force/test_task_force_composition_audit.py
uv run pytest -q

git status --short
```

No commit or push is required for this validation step.
