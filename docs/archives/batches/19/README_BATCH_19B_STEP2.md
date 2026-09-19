# Batch 19b — Step 2 — Candidate Campaign Execution

Baseline: Batch 19a Steps 1–3 + Batch 19b Step 1 + Step 1 hotfix installed locally.

This overlay connects the deterministic recruitment campaign plan to the existing Batch 16 Historical Replay/PAPER evaluation path.

## Guarantees

- exactly two twins: `BASELINE` and `WITH_CANDIDATE`;
- incumbent specialist roster must match the frozen campaign baseline exactly;
- candidate specialist is injected only into the `WITH_CANDIDATE` twin under the evaluation-only `candidate:<recruitment_id>` identity;
- fresh replay runner and fresh PAPER broker are mandatory for each twin;
- wrong replay `run_id` is rejected;
- period role comes from the frozen campaign plan;
- no success-criteria comparison yet;
- no promotion recommendation;
- no `AgentRegistryEntry` creation or registry mutation;
- no Risk Engine modification and no LIVE execution path.

## Validation

From repository root:

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Do not commit or push until these outputs have been reviewed. Do not use `git add -A`.
