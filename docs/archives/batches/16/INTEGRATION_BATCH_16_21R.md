# Batch 16.21r — Denver Realized Setup Attribution

## Goal

Replace Denver's post-hoc `timestamp + average price + quantity` trade matcher for real
historical evaluation bundles with exact PAPER execution provenance.

## Real attribution path

- Each executed pipeline setup is bound to its PAPER `fill_id` and original `opportunity_id`.
- The complete Batch 10 evaluation execution stream is replayed in fill order.
- Same-direction entries become explicit setup lots inside the existing average-cost position.
- A realized close allocates the evaluated `ClosedTrade.net_pnl` pro-rata to the quantities
  still owned by those setup lots.
- Quantity and PnL are conserved exactly; the evaluated trading result is never recomputed.
- Partial closes accumulate on the setup lots. A Denver observation is emitted only when the
  position cycle is fully closed, so an opportunity remains one statistical sample.
- Reversal fills close the previous setup lots and attribute only the residual new exposure to
  the reversing opportunity.
- Open/incomplete setup outcomes at the period boundary are not promoted into Denver history.

## Fail-closed invariants

The catalog remains unavailable if fill provenance is missing, duplicate, inconsistent with the
evaluation stream, or if the evaluated closed trades cannot be consumed exactly.

Synthetic legacy tests/bundles that do not expose `EvaluationSource.executions` keep the previous
strict exact-entry matcher and therefore still fail closed on ambiguous scaled trades.

## Unchanged

Scanner, MTF, agent orchestration, Rio, Risk Engine, PaperBroker execution, trading PnL,
DESIGN/VALIDATION/OOS semantics, frozen Denver prior policy, and LIVE/PAPER safety are unchanged.
