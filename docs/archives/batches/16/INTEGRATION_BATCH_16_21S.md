# Batch 16.21s — Same-Timestamp Fill Ordering

## Goal

Preserve the real `PaperBroker` execution sequence when two or more fills share the
same timestamp.

## Root cause

`PaperBroker.get_fills()` preserves insertion order, which is the real economic
execution order. Batch 10 Evaluation and Batch 16.21r Denver attribution were both
sorting executions by `(filled_at, fill_id)`.

Historical lifecycle exits are processed before the scanner/pipeline decision on a
candle. They can therefore share exactly the same timestamp with a new pipeline
entry. `fill_id` is an opaque identifier and must not be used as an economic
tie-breaker. Reordering equal-timestamp fills can manufacture a synthetic reversal,
change which fill closes a trade, and leave Denver with residual exposure that has
no setup provenance.

## Fix

- Batch 10 Evaluation sorts only by `filled_at`.
- Python's stable sort preserves the existing `EvaluationSource.executions` order
  for equal timestamps.
- That source order comes directly from the `PaperBroker` fill insertion order.
- Denver applies the exact same stable timestamp ordering.

## Regression coverage

- Evaluation: lifecycle close followed by a new opposite-side entry at the same
  timestamp remains in broker source order even when the fill IDs sort the other way.
- Denver: the lifecycle close is attributed to the old setup and the subsequent
  same-timestamp entry opens the new setup without synthetic reversal ambiguity.

## Unchanged

Scanner, MTF, agent orchestration, Rio, Risk Engine, PaperBroker execution,
fees/slippage formulas, position accounting rules, DESIGN/VALIDATION/OOS semantics,
and frozen Denver prior policy are unchanged.
