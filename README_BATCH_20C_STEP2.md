# Batch 20c — Step 2 — Multi-member AI Execution

This overlay adds the first runtime that actually executes Task Force members through the
existing structured AI Gateway contract.

## Scope

The runtime is intentionally narrow:

- execute one logical structured AI call per Task Force member;
- execute members sequentially in the deterministic contract order;
- require the Batch 20a compute gate before every member call;
- call only `generate_structured(...)` on the AI Gateway contract;
- validate Task Force member identity after structured output parsing;
- account known AI cost from all returned `usage_records`;
- stop immediately on any gate, Gateway, output, retry-envelope, or accounting failure;
- never create a `TradeProposal`, Risk decision, broker action, registry mutation, or LIVE action.

Aggregation and optional Red Team synthesis remain deferred to Batch 20c Step 3.

## Explicit compute quote

The current AI Gateway does not expose a public route-cost estimator or a per-request
`max_attempts`. Therefore each member call requires an explicit
`TaskForceMemberComputeQuote` with:

- `requested_eur`: maximum Task-Force-authorized EUR envelope for the logical call;
- `gateway_max_attempts`: maximum Gateway attempts covered by that envelope;
- an audit `quote_id` and textual `basis`.

`gateway_max_attempts - 1` is passed to the existing Task Force compute gate as the maximum
retry index for that logical call. A blocked decision prevents the Gateway call.

The AI Gateway hard budget remains independently authoritative. A Task Force `ALLOW` never
bypasses the Gateway budget ledger.

## Cost accounting

On successful Gateway return, the runtime sums every returned `usage_record.estimated_cost`
for the logical call. This captures successful structured-output retries returned by the
Gateway result.

If the Gateway raises an exception, a provider attempt may already have consumed budget but
no `AIGatewayResult` is available to the Task Force runtime. The run therefore stops
immediately and records `cost_accounting_complete=False`; no later member is called.

If a returned actual cost exceeds the explicit quote, or the returned attempt count exceeds
the declared attempt envelope, the run fails closed after recording the known charge.

## Runtime result

`TaskForceMultiMemberExecution` is immutable and returns one of:

- `COMPLETED`: every member has a valid structured analysis and accounting is complete;
- `BLOCKED`: the Task Force compute gate refused a member before the Gateway call;
- `FAILED`: Gateway, result identity, output identity, or post-call accounting failed.

Only a completed run has `aggregation_ready=True`.

Every runtime result keeps these authorities false:

- `trade_proposal_authority=False`;
- `registry_mutation=False`;
- `risk_authority=False`;
- `live_authority=False`.

## Files

- `app/task_force/execution_runtime.py`
- `app/task_force/__init__.py`
- `tests/task_force/test_task_force_execution_runtime.py`
- `README_BATCH_20C_STEP2.md`
- `CHANGELOG_BATCH_20C_STEP2.md`

## Local validation

After extracting at repository root:

```powershell
uv run pytest -q tests/task_force/test_task_force_execution_runtime.py
uv run pytest -q
git status --short
```

No commit or push is part of this overlay.
