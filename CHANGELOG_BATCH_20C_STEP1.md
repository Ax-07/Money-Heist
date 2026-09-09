# Changelog — Batch 20c Step 1

## Added

- analysis-only Task Force execution contract;
- explicit gate + lifecycle approval readiness validation;
- deterministic per-run/per-member AI Gateway request IDs;
- real `AIGatewayRequest` construction without provider execution;
- neutral grounded `TaskForceMemberAnalysis` structured output;
- fail-closed output identity validation;
- audit bindings to Batch 20b integration, exact plan, plan gate, and lifecycle approval.

## Preserved invariants

- no automatic `AgentRegistry` mutation;
- no Task Force-created agent permissions;
- no direct provider calls outside the AI Gateway;
- no `TradeProposal` authority;
- no Risk Engine authority;
- no broker or LIVE authority;
- Task Force compute limits do not replace the AI Gateway hard budget.
