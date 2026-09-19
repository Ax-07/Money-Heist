# Batch 21e — Step 6 — Historical Multi-Crew Lifecycle & Virtual Lots

Baseline: `2c38bc3` — Step 5 Historical Master PAPER Execution / Single-Capital Accounting.

## Goal

Continue the coordinated Master historical replay after PAPER entry execution while preserving one
physical Master account and separate logical ownership for every crew trade.

The Step 6 path is:

`Step 5 EXECUTED entry -> virtual lot registration -> future OPEN/CLOSE barriers -> deterministic
stop/target resolution -> one Master PAPER exit order -> virtual lot CLOSED -> reservation RELEASED`.

A virtual lot is accounting and lifecycle attribution only. It is not a broker account, a second
position engine, a new Risk authority or cloned capital.

## One physical position, several logical lots

`MasterHistoricalVirtualLotBook` is attached to the exact Step 5
`MasterHistoricalPaperRuntime`. It never creates another broker.

Each successful Step 5 entry becomes one immutable `MasterHistoricalVirtualLot` binding:

- source `system_id`;
- proposal and proposal fingerprint;
- Step 5 execution attempt fingerprint;
- exact `reservation_id`;
- exact filled quantity and entry price;
- entry fee;
- stop and targets from the exact proposal evidence;
- local Risk open-risk amount and gross-exposure amount from the committed reservation;
- entry candle index and timestamp.

The physical broker keeps only its existing net position per symbol. The virtual book keeps the
individual logical lots. Step 6 continuously checks:

`physical broker signed quantity == sum(open virtual lot signed quantities)`.

This remains valid when crews oppose each other. For example, a LONG 0.1 and SHORT 0.1 may net to a
flat physical broker position while both virtual lots remain open. If the LONG later exits, the Master
broker sends the corresponding SELL 0.1 and becomes physically SHORT 0.1, exactly matching the
remaining SHORT virtual lot.

No branch equity is created or summed.

## Registration boundary

Virtual lots are registered only from exact Step 5 `EXECUTED` attempts.

Registration requires:

- exact plan, timeline and decision barrier provenance;
- exact Step 5 runtime fingerprint;
- exact Step 5 final reservation ledger;
- exact source candle fingerprint;
- proposal evidence matching the executed Step 5 entries exactly;
- every source reservation still `COMMITTED`.

Step 5 attempts blocked by physical Master cash, non-reserved candidates and Master-rejected
candidates never create virtual lots.

Registration is deterministic and idempotent.

## Entry-candle protection

A lot stores the candle index on which its Step 5 entry filled.

It is never eligible for stop/target resolution on that same candle. This preserves the existing
historical backtest rule that a position created at a fully known candle close cannot retroactively
use that candle's high/low.

The next candle is eligible even when its OPEN timestamp equals the previous CLOSE timestamp because
eligibility is based on candle index, not only wall-clock comparison.

## OPEN/CLOSE lifecycle

Step 6 reuses the existing pure `resolve_intrabar()` logic and the existing `STOP_FIRST` policy.

Barriers must be processed contiguously and in the exact timeline order.

At `CANDLE_OPEN`:

- only gap exits are eligible;
- non-gap intrabar touches are deferred to CLOSE.

At `CANDLE_CLOSE`:

- non-gap stop/target touches are resolved;
- an unresolved gap is a hard sequencing error.

The raw candle must reproduce the exact timeline candle fingerprint before any lifecycle action.

## Exit execution semantics

Stop exits reuse existing PAPER market-order semantics:

- adverse reference price from `resolve_intrabar()`;
- existing plan market slippage;
- existing taker fee;
- exact lot quantity;
- opposite side to the virtual lot.

Target exits reuse existing historical lifecycle semantics:

- exact first target selected by `resolve_intrabar()`;
- existing PAPER limit order;
- fill capped at the target price;
- existing maker fee;
- no favorable gap improvement;
- exact lot quantity.

Several exits on the same barrier are ordered canonically by lot provenance. This ordering is only a
deterministic execution sequence; it does not rank crews or change admission priority.

No exit can resize or increase a Risk-authorized quantity.

## Reservation lifecycle

An OPEN virtual lot must retain its exact `COMMITTED` Master reservation.

After a successful historical exit, that reservation is released through the existing 21b ledger at
the exact barrier timestamp with a deterministic release reference.

Only the reservation belonging to the exited lot is released. Other crew reservations remain
unchanged.

The virtual lot then becomes immutable `CLOSED` evidence with:

- exit reason;
- reference price;
- PAPER fill price and fee;
- broker order/fill IDs;
- reservation release reference;
- gross realized PnL;
- net realized PnL after entry and exit fees.

## Gross exposure versus physical net exposure

The Master PAPER account remains the only capital truth, but portfolio risk observation cannot use
only the broker's net exposure when crews hold offsetting logical trades.

`build_master_historical_virtual_portfolio_snapshot()` therefore projects:

- Master capital from the one physical Step 5 broker account;
- per-crew open-position count from virtual lots;
- per-crew open risk from exact committed reservation risk;
- per-crew gross exposure from each open lot quantity marked at the supplied market price.

Opposing virtual lots therefore do not disappear from gross exposure simply because the physical
broker position nets to zero.

If marked virtual gross exposure rises above the gross amount committed in the reservation ledger,
Step 6 does **not** enlarge the reservation. The existing reconciliation layer becomes
`INCONSISTENT`, which is intentionally fail-closed for later Master admission.

This avoids inventing dynamic exposure capacity or leverage.

## Determinism and replay safety

Step 6 uses stable SHA-256 fingerprints for lots, registrations, exits, book snapshots and barrier
results.

Immediate replay of the exact latest processed barrier is idempotent and creates no duplicate order.
Replaying an older barrier after the lifecycle has progressed fails closed.

A missing or externally released reservation, stale ledger, changed proposal, changed candle,
skipped barrier or physical/logical net mismatch fails before further lifecycle progression.

## Authority invariants

Step 6:

- uses the exact one Master PAPER broker from Step 5;
- never creates a broker per crew;
- never sums branch equities;
- has no LIVE path;
- has no Risk authority;
- has no Master admission authority;
- has no registry authority;
- cannot promote agents;
- cannot change allocation, Risk Gate or arbitration policies;
- cannot infer additional capital;
- cannot resize an admitted trade.

`paper_broker_authority = True` is limited to deterministic PAPER exit execution for already-open
virtual lots. It grants no LIVE or Risk authority.

## Contracts

Step 6 adds:

- `MasterHistoricalVirtualLotStatus`;
- `MasterHistoricalVirtualLot`;
- `MasterHistoricalVirtualLotBook`;
- `MasterHistoricalVirtualLotBookSnapshot`;
- `MasterHistoricalVirtualLotRegistrationStatus`;
- `MasterHistoricalVirtualLotRegistrationResult`;
- `MasterHistoricalVirtualLotExitEvent`;
- `MasterHistoricalLifecycleStatus`;
- `MasterHistoricalLifecycleResult`;
- `build_master_historical_virtual_lot_book()`;
- `register_master_historical_virtual_lots()`;
- `process_master_historical_virtual_lot_barrier()`;
- `build_master_historical_virtual_portfolio_snapshot()`.

## Explicit Step 6 boundary

Step 6 provides the multi-crew lifecycle primitive but does not yet assemble the entire replay loop
that, on every CLOSE barrier, performs lifecycle -> current Master snapshot -> local crew decisions ->
reservation/arbitration -> Step 5 entries -> virtual-lot registration.

It also does not introduce trailing stops, partial targets, scale-outs, statistical correlation,
dynamic allocation, Kelly sizing or LIVE execution.

The next integration step can use the Step 6 portfolio projection as the current state for subsequent
Master Risk Gate evaluations and then build final historical evaluation metrics.

## Validation in generation harness

- `tests/portfolio/test_master_historical_replay_virtual_lifecycle.py`: 31 passed;
- all reconstructed `tests/portfolio`: 508 passed;
- Python compilation: passed;
- Python source/test line length <= 100: passed.

The generation harness does not contain Ruff. Run Ruff and the complete repository suite in the real
checkout before commit.
