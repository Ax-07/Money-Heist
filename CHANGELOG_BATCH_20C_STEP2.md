# CHANGELOG — Batch 20c Step 2

## Added

- `TaskForceMemberComputeQuote` for explicit per-member logical-call cost/retry envelopes.
- Immutable Task Force runtime usage snapshots.
- `TaskForceMemberExecutionRecord` with compute-gate provenance and actual Gateway usage cost.
- Fail-closed execution statuses and failure stages.
- Sequential `execute_task_force_members(...)` runtime.
- Exact member-context and compute-quote coverage validation.
- Pre-call Task Force compute gate enforcement.
- Real structured Gateway invocation through `generate_structured(...)` only.
- Gateway result identity validation and Task Force member output identity validation.
- Actual cost accounting across returned Gateway usage records.
- Post-call quote and attempt-envelope enforcement.
- Explicit partial-accounting marker for Gateway exceptions without a returned usage result.

## Safety invariants preserved

- No direct AI provider access.
- No bypass of the AI Gateway hard budget.
- No `TradeProposal` authority.
- No Risk Engine authority.
- No broker/exchange authority.
- No AgentRegistry mutation.
- No LIVE authority.
- No automatic lifecycle promotion or registry-state mutation.

## Deferred

- Cross-member aggregation and synthesis.
- Optional Palermo / Red Team review of the Task Force synthesis.
- Main orchestration integration.
