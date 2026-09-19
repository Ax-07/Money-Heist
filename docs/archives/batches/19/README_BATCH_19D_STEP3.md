# Batch 19d — Step 3 — Advisory Audit, Reproducibility & Stale-Plan Guards

This overlay closes the Recruitment Advisory block with an immutable audit lineage and fail-closed freshness checks.

## Added

- `RecruitmentAdvisoryAuditRecord`
- `RecruitmentAdvisoryAuditValidation`
- `RecruitmentAdvisoryAuditFreshness` (`FRESH` / `STALE`)
- `build_recruitment_advisory_audit(...)`
- `revalidate_recruitment_advisory_audit(...)`
- `require_fresh_recruitment_advisory_audit(...)`
- `assert_recruitment_advisory_audit_reproducible(...)`

The audit freezes:

`CandidateSpec -> EvidencePackage -> Advisory -> AdvisoryTransitionPlan -> CapacityPolicy/Snapshot`

A READY plan becomes stale if any audited material context changes, including lifecycle revision/state, candidate spec, evidence package, advisory, transition planning, capacity policy, capacity snapshot, period, status, or transition id.

`FRESH` never authorizes execution. Operator authorization remains mandatory and this module never calls `record_recruitment_transition`.

## Safety invariants

- no registry mutation;
- no automatic lifecycle transition;
- no automatic promotion;
- no LIVE authority;
- no Risk Engine dependency;
- no `AgentRegistryEntry` dependency;
- stale plan fails closed.

## Local validation

Run after extraction at repository root:

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Do not commit or push until both test runs are green.
