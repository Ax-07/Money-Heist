# Batch 21b — Step 1 — Static Allocation Policy Contracts

This step introduces immutable, operator-owned Master Portfolio allocation policy contracts only.

## Scope

- `CrewAllocationEnvelope` with explicit static ceilings for capital, open risk and gross exposure.
- `MasterAllocationPolicy` with deterministic member/envelope ordering and SHA-256 fingerprinting.
- `CONFIGURED` / `NOT_CONFIGURED` fail-closed state.
- Explicit operator provenance through `OPERATOR_CONFIGURATION` and optional `source_ref`.

## Safety boundaries

This step does **not**:

- transfer or clone capital to crews;
- normalize envelope ceilings into percentages or weights;
- require envelope sums to equal or stay below Master equity;
- reserve, commit or release capacity;
- admit or reject trade proposals;
- call or modify the Risk Engine;
- modify Paper Broker, Paper Pipeline or LIVE execution;
- use reputation, recruitment, Task Force or AI to change allocation;
- provide automatic, dynamic, registry, risk or LIVE authority.

An envelope is a ceiling, not a cash account. Global physical capital remains the single Master capital truth created in Batch 21a. Actual global availability and double-spend prevention belong to the reservation ledger in a later Batch 21b step.

## Validation

Run:

```powershell
uv run ruff check app/portfolio tests/portfolio/test_master_allocation_policy.py
uv run pytest -q tests/portfolio/test_master_allocation_policy.py
uv run pytest -q tests/portfolio
uv run pytest -q
git status --short
```
