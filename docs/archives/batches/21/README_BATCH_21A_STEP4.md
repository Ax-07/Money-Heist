# Batch 21a — Step 4 — Master Portfolio Snapshot Audit & Provenance Seal

## Scope

Step 4 seals the provenance of an already-built `MasterPortfolioSnapshot` without
re-reading any provider, broker, Risk component, Task Force, Recruitment service, or LIVE
boundary.

It adds:

- `PortfolioAuditSourceKind`;
- `PortfolioSourceAuditRecord`;
- `MasterPortfolioAuditSeal`;
- `build_master_portfolio_audit_seal()`;
- deterministic audit fingerprints bound to the existing snapshot fingerprint.

## Invariants

- Exactly one Master capital source is sealed.
- Every crew exposure source is sealed with `system_id`, membership reference, source,
  source reference, availability, and reason code when unavailable.
- The audit seal is derived only from the immutable Master snapshot; it does not re-read
  local providers and therefore cannot create a second observation truth.
- Source records are stored in canonical order.
- Equivalent observations produce the same audit fingerprint regardless of construction order.
- Material provenance or membership changes produce a different fingerprint.
- `UNAVAILABLE` remains explicit; absence is never converted to zero or guessed data.
- No capital allocation, reservation, risk decision, broker execution, registry mutation,
  Task Force authority, or LIVE authority is introduced.

## Validation

Run from the repository root:

```powershell
uv run ruff check app/portfolio tests/portfolio/test_master_audit.py
uv run pytest -q tests/portfolio/test_master_snapshot.py tests/portfolio/test_master_observation.py tests/portfolio/test_master_fleet.py tests/portfolio/test_master_audit.py
uv run pytest -q
git status --short
```
