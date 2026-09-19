# Batch 21c — Step 1: Master Portfolio Risk Gate Contracts

Baseline: `45c016f feat(portfolio): add reservation audit closure`

## Scope

This step adds immutable contracts for the future Master Portfolio Risk Gate. It does **not**
evaluate a candidate, mutate the reservation ledger, build an order intent, call a broker, or
change PAPER/LIVE execution.

The constitutional relation remains:

`Local Risk authorized AND Master Gate ADMIT AND existing execution gates authorized`

The Master gate is **veto-only**. It cannot turn a local `REJECTED` decision into `ADMIT`, cannot
increase or resize locally approved amounts, and cannot modify local Risk limits.

## Added contracts

- `MasterRiskGatePolicyStatus`
- `MasterRiskGatePolicySource`
- `MasterRiskGateDecisionStatus`
- `MasterRiskGateReasonCode`
- `MasterRiskGatePolicy`
- `MasterRiskGateCandidate`
- `MasterRiskGateDecision`
- `build_master_risk_gate_policy()`
- `build_master_risk_gate_candidate()`

A generic public `ADMIT` builder is intentionally **not** exported. Step 2 will add the
deterministic evaluator that is allowed to produce gate decisions.

## Operator-owned global limits

V1 exposes only limits that can be evaluated conservatively from already existing Master
Portfolio and reservation data:

- `max_total_open_risk_amount`
- `max_total_gross_exposure_amount`

Both must be explicitly configured together. No numeric default is inferred. A
`NOT_CONFIGURED` policy carries no numeric limits and requires an operator-owned reason code.

A global max-position rule is intentionally deferred: the current PAPER boundary does not yet
provide a trustworthy Master-level position-count delta for a candidate. Symbol concentration,
correlation matrices, Kelly sizing, reputation-weighted limits and adaptive allocation are also
out of scope.

## Local Risk binding

`build_master_risk_gate_candidate()` binds one existing `RiskDecision` to:

- one `master_portfolio_id`;
- one `system_id`;
- the local `proposal_id`;
- the exact local approved quantity/risk/notional;
- the local Risk decision timestamp and reason codes;
- one existing reservation id when local Risk is `APPROVED` or `RESIZED`;
- stable SHA-256 fingerprints.

A local `REJECTED` decision cannot carry a reservation or non-zero approved amounts.

## Decision invariants

`MasterRiskGateDecision` only permits:

- `ADMIT`: local Risk must already be `APPROVED` or `RESIZED`, and admitted quantity/risk/notional
  must exactly equal local Risk-approved values;
- `REJECT`: admitted quantity/risk/notional are always zero.

The contract explicitly carries:

- `veto_only=True`;
- `local_risk_override=False`;
- `resize_applied=False`;
- `risk_authority=False`;
- `admission_authority=True` only for the Master portfolio admission result;
- `reservation_mutation=False`;
- `broker_authority=False`;
- `registry_mutation=False`;
- `live_authority=False`;
- `auto_execute=False`.

## Explicitly not included

- no evaluator yet;
- no PaperTradingPipeline modification;
- no OrderIntent modification;
- no reservation mutation;
- no RiskEngine modification;
- no broker call;
- no LIVE import or activation path;
- no Task Force, Recruitment, Reputation, AgentRegistry or Master Professor authority;
- no correlation or concentration heuristic.

## Validation commands

```powershell
uv run ruff check app/portfolio tests/portfolio/test_master_risk_gate_contracts.py
uv run pytest -q tests/portfolio/test_master_risk_gate_contracts.py
uv run pytest -q tests/portfolio
uv run pytest -q
git status --short
```
