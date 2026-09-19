# Batch 19c — Step 3 — Auditable Candidate Evidence Package

This overlay completes Batch 19c by introducing a deterministic, immutable evidence package for one recruitment candidate.

## Added

- `app/recruitment/evidence_package.py`
- exports in `app/recruitment/__init__.py`
- focused evidence-package tests and boundary tests

## Contract

`build_candidate_evidence_package(...)` recomputes and verifies the complete evidence chain before packaging it:

1. comparability/OOS evidence gate;
2. Recruitment → Batch 18 ablation bridge;
3. Batch 18 reputation dimensions + candidate cost evidence;
4. frozen success-criteria snapshot;
5. exact lineage/fingerprints for campaign, execution, runs and business outputs.

The package is evidence only:

- `criteria_evaluation_performed = False`
- `recommendation_generated = False`
- `auto_apply = False`
- `registry_mutation = False`
- `promotion_action = False`
- `live_authority = False`

A candidate spec is reconstructed against the frozen campaign identity. Post-planning changes to budget, model class, tools, success criteria, or other candidate fields are rejected.

The package fingerprint is also checked by the dataclass itself, so a stale/tampered payload cannot be reconstructed with the previous fingerprint.

## Local validation

From the repository root:

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Do not commit/push until the local suite is green. Do not use `git add -A`.
