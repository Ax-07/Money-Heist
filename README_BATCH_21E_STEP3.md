# Batch 21e — Step 3 — Historical Master Decision Barrier / Pre-Execution Integration

Baseline: `fbd769f` — Master Historical Replay Coordinator.

## Goal

Seal every crew's historical decision at one exact decision-eligible `CANDLE_CLOSE` barrier while
stopping strictly before Master reservation, Master Risk Gate admission, arbitration, PAPER broker
execution, or any LIVE path.

Step 3 consumes pre-execution evidence already produced through the existing crew stack:

- the exact `FeatureSnapshot` / market context observed at the CLOSE barrier;
- the optional scanner opportunity;
- the existing orchestration result;
- when orchestration produced a `TRADE_PROPOSAL`, the existing deterministic local `RiskDecision`.

It does not introduce a second Risk Engine and does not run a broker.

## Why the local Risk decision is supplied

The current single-system PAPER pipeline couples orchestration, local Risk and broker execution in
one method. Replaying that complete method independently for each crew would execute trades before
Master reservation and arbitration.

Step 3 therefore defines the immutable integration boundary after local Risk but before broker.
The caller must stop the crew stack at that point and provide the resulting evidence.

This also avoids inventing a new historical crew-equity model in Step 3. The existing branch
`initial_balance` values remain provenance only and are never promoted to Master capital.

## Exact CLOSE-barrier binding

`build_master_historical_decision_barrier()` accepts only a barrier that:

- belongs exactly to the supplied Step 2 timeline;
- is a `CANDLE_CLOSE` barrier;
- is decision eligible;
- carries the exact timeline crew membership.

Every crew must provide exactly one evidence record. Caller order is canonicalized by `system_id`.

Every supplied market context must match the Master plan symbol/timeframe and have
`observed_at == barrier.observed_at` exactly.

## Terminal crew outcomes

The builder records one immutable outcome per crew:

- `NO_OPPORTUNITY`;
- `NO_ANALYSIS`;
- `NO_TRADE`;
- `ORCHESTRATION_FAILED`;
- `LOCAL_RISK_REJECTED`;
- `LOCAL_RISK_AUTHORIZED`.

`NO_OPPORTUNITY`, `NO_ANALYSIS`, `NO_TRADE` and orchestration failure are terminal before Risk.
A locally `REJECTED` trade is terminal and cannot produce a Master candidate seed.

## Candidate seed before reservation

Only local Risk `APPROVED` / `RESIZED` decisions create a `MasterHistoricalCandidateSeed`.

The seed seals:

- Master plan, timeline and exact CLOSE barrier provenance;
- market-context fingerprint;
- opportunity fingerprint;
- orchestration fingerprint;
- proposal ID and fingerprint;
- exact local Risk status, reason codes, approved quantity, approved risk and approved notional;
- local Risk decision time and details;
- exact local Risk decision fingerprint used by Batch 21c.

The seed deliberately has no `reservation_id`.

It exposes:

- `reservation_required = True`;
- `reservation_id_present = False`;
- `capital_requirement_inferred = False`.

The approved notional is not silently treated as reservation capital. Step 3 does not infer leverage
or a capital requirement. A later step must provide an explicit `capital_amount` when constructing
the existing Batch 21b `ReservationRequest`.

## Deterministic local Risk chronology

For a `TRADE_PROPOSAL`, the supplied local `RiskDecision` must:

- bind the exact proposal ID;
- have a supported status (`REJECTED`, `APPROVED`, `RESIZED`);
- contain non-duplicated reason codes;
- have `created_at == barrier.observed_at` exactly.

Authorized decisions must carry positive approved quantity, risk and notional. Rejected decisions
must carry zero approved amounts.

`MasterHistoricalCandidateSeed.to_local_risk_decision()` reconstructs the exact decision binding so
the next step can call the existing Batch 21c candidate builder after reservation without inventing
a parallel local Risk representation.

## Single Master capital truth

Step 3 never reads or sums branch broker equities.

The result preserves:

- `single_master_capital = True`;
- `sums_branch_equities = False`.

No source branch balance becomes cash, allocation, reservation capacity, or executable buying power.

## Authority invariants

The decision barrier is evidence only:

- `mutation_applied = False`;
- `reservation_mutation = False`;
- `broker_called = False`;
- `risk_authority = False`;
- `admission_authority = False`;
- `broker_authority = False`;
- `live_authority = False`;
- `auto_execute = False`.

The seed is not an order and cannot be sent to a broker. Local Risk authority remains in the existing
Risk Engine decision. Master admission authority remains in the later existing Master Risk Gate.

## Contracts

Step 3 adds:

- `HistoricalCrewDecisionStatus`;
- `HistoricalCrewPreExecutionEvidence`;
- `HistoricalCrewDecisionOutcome`;
- `MasterHistoricalCandidateSeed`;
- `MasterHistoricalDecisionBarrierStatus`;
- `MasterHistoricalDecisionBarrier`;
- `build_master_historical_decision_barrier()`.

Every persisted output has a deterministic SHA-256 fingerprint.

## Next step

Step 4 should bridge each `MasterHistoricalCandidateSeed` into the existing Batch 21b reservation
ledger using an explicit caller-supplied capital requirement, then build the existing Batch 21c
`MasterRiskGateCandidate` with the resulting `reservation_id` and feed the existing Batch 21d
arbitration chain.

It must still stop before broker execution unless the Master-admitted PAPER execution/accounting
model has one explicit physical capital truth.

## Validation in generation harness

- `tests/portfolio/test_master_historical_replay_preexecution.py`: 37 passed;
- all `tests/portfolio`: 401 passed;
- Python 3.13 compilation: passed;
- Python source line length <= 100: passed.

Ruff is not installed in the generation harness. Run Ruff and the complete repository suite in the
real checkout before commit.
