# Batch 20c — Step 1 — Execution Contracts

## Goal

Introduce the analysis-only execution contract that hands a closed Batch 20b composition to
future multi-member execution through the existing AI Gateway.

This step builds real `AIGatewayRequest` objects but deliberately does **not** call the gateway,
any provider, the Risk Engine, a broker, or LIVE execution.

## Added contracts

- `TaskForceMemberFinding`
- `TaskForceMemberAnalysis`
- `TaskForceMemberExecutionSpec`
- `TaskForceExecutionContract`
- `build_task_force_execution_contract(...)`
- `build_member_ai_gateway_request(...)`
- `validate_task_force_member_analysis(...)`

## Readiness requirements

An execution contract can be prepared only when:

- the Batch 20b composition closure still matches its exact plan fingerprint;
- the Task Force plan gate is `ALLOW`;
- the gate request, policy, and composition fingerprints match the closed plan;
- the Task Force lifecycle is `APPROVED_FOR_EXECUTION`;
- the lifecycle contains approval transition evidence;
- the request fingerprint is still current;
- the lifecycle and plan identities/fingerprints still match;
- preparation happens after lifecycle approval and before expiry.

The resulting authorization is intentionally narrow:

- `member_analysis_authorized = True`;
- `gateway_required = True`;
- `gateway_calls_performed = False`;
- `trade_proposal_authority = False`;
- `registry_mutation = False`;
- `risk_authority = False`;
- `live_authority = False`.

## AI Gateway binding

Each member spec preserves the registry-backed:

- `agent_id`;
- `prompt_version`;
- `model_route`;
- Task Force tool allowlist audit snapshot;
- member budget and call limit.

Each execution run receives deterministic per-member UUIDv5 gateway request IDs. A different
`execution_run_id` creates different request IDs while preserving replayability within one run.

`build_member_ai_gateway_request(...)` requires a non-empty, JSON-serializable materialized
context. It uses the existing `AIGatewayRequest` contract and includes Task Force provenance in
metadata. It never invokes the gateway itself.

## Structured output

`TaskForceMemberAnalysis` is intentionally neutral and advisory. It supports grounded findings,
uncertainties, follow-up questions, and confidence without creating `TradeProposal`, Risk, broker,
registry, or LIVE authority.

`validate_task_force_member_analysis(...)` fails closed if structured output claims another Task
Force, execution run, member, or agent identity.

## Deferred to Step 2

Batch 20c Step 2 will implement actual multi-member AI execution. Before every model call it must
still pass:

1. the Task Force compute gate from Batch 20a Step 3; and
2. the existing AI Gateway hard budget and provider routing logic.

No Task Force budget replaces the existing global AI Gateway budget ledger.

## Validation

Targeted:

```powershell
uv run pytest -q tests/task_force/test_task_force_execution.py
```

Then full suite:

```powershell
uv run pytest -q
git status --short
```

Do not commit or push until local validation is confirmed.
