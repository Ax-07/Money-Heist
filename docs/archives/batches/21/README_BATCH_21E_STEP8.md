# Batch 21e — Step 8 — Master Historical Replay Closure & Audit Seal

Baseline: `593385c` — Step 7 Coordinated Multi-Barrier Replay & Master Evaluation.

## Goal

Close Batch 21e with a deterministic, read-only audit artifact over one already completed coordinated
Master historical replay.

Step 8 does not replay candles, call the historical input port, call an AI provider, submit PAPER
orders, release reservations, mutate virtual lots, change policies, or touch LIVE. It only verifies
that the complete Step 1→7 provenance graph is internally coherent and then seals the verified state.

The audited chain is:

`plan -> timeline -> lifecycle barriers -> decision cycles -> local Risk evidence -> reservations ->
Master arbitration -> Master PAPER entries -> virtual-lot registration -> virtual-lot exits -> final
ledger/book/account evidence -> Master evaluation`.

## Two immutable artifacts

Step 8 adds:

- `MasterHistoricalReplayAuditReport` with status `VERIFIED`;
- `MasterHistoricalReplayClosureSeal` with status `SEALED`.

Both records are SHA-256 fingerprinted and contain no mutation, Risk, admission, registry, broker or
LIVE authority.

The seal is created only after the full audit succeeds.

## Static provenance verification

The audit recomputes and checks the exact fingerprints of:

- `MasterHistoricalReplayPlan`;
- `MasterHistoricalReplayTimeline`;
- `MasterAllocationPolicy`;
- `MasterRiskGatePolicy`;
- `MasterArbitrationPolicy`;
- `MasterHistoricalCoordinatedReplayResult`.

It verifies that plan, timeline, policies and result all belong to the same Master Portfolio and that
the policy fingerprints embedded in the plan and result still match the exact supplied policies.

Crew membership must be identical across plan, timeline and allocation policy.

## Full barrier coverage

Step 8 requires exactly one lifecycle result and one equity point for every timeline barrier.

Decision cycles must exist for exactly every decision-eligible `CANDLE_CLOSE`, with no missing,
additional or reordered cycle.

Each lifecycle result must bind the exact timeline:

- barrier sequence;
- candle index;
- OPEN/CLOSE phase;
- observed timestamp;
- barrier fingerprint;
- plan fingerprint;
- timeline fingerprint;
- virtual-lot book identity.

## Ledger continuity

The audit reconstructs only the empty opening reservation-ledger snapshot from the already supplied
opening snapshot and static allocation policy. It never mutates the replay ledger.

It then verifies the state chain:

`previous ledger -> lifecycle before/after -> Step 4 initial/final -> Step 5 initial/final -> Step 6
registration -> next lifecycle`.

This detects a replay assembled from individually valid records that do not belong to the same state
history.

At closure:

- no reservation may remain `RESERVED`;
- each `COMMITTED` reservation must correspond to exactly one OPEN virtual lot;
- each OPEN lot must bind the same crew, proposal, open-risk amount and committed gross amount as its
  reservation;
- RELEASED reservations may represent normal closed lots or deterministic pre-execution release paths
  such as the Step 5 physical-cash veto.

## Account/equity continuity

Every equity point must bind the account fingerprint produced at that exact barrier.

For non-decision barriers this is the lifecycle account-after fingerprint. For decision barriers it is
the Step 5 account-after fingerprint after any admitted entry execution.

The final account fingerprint must equal the final equity point account fingerprint.

Step 8 does not call the broker to reconstruct a second account view.

## Nested fingerprint integrity

The audit re-hashes the persisted Step 3→7 artifacts rather than trusting their stored fingerprints.
This includes:

- barrier inputs;
- decision barriers;
- reservation/arbitration results;
- PAPER execution results;
- virtual-lot registrations;
- lifecycle results;
- decision cycles;
- equity points;
- final virtual-lot book;
- final reservation ledger;
- Master evaluation and per-crew evaluation records.

Post-construction tampering therefore fails closed even when a caller mutates a frozen object through
unsafe runtime techniques.

## Single physical Master capital

Closure requires the same invariant established throughout Batch 21:

- `plan.master_initial_capital` is the only opening physical-capital truth;
- opening Master equity and cash equal this amount;
- reservation-ledger Master capacity equals this amount;
- evaluation initial capital equals this amount;
- branch `BacktestRun.config.initial_balance` values remain non-summable provenance;
- the coordinated result cannot declare branch brokers or summed branch equity.

The audit does not compare the Master amount against the numerical sum of source-branch balances,
because equality could happen by coincidence. It verifies structural provenance and authority flags
instead.

## Virtual-lot and evaluation accounting

The final virtual-lot book remains the attribution truth for crew trades while the Master account
remains the capital truth.

Step 8 verifies:

- PAPER entry count = CLOSED lots + OPEN lots;
- final open risk = final book committed open risk;
- final virtual gross exposure = final book virtual gross exposure;
- closed-lot realized net PnL = final book realized virtual PnL;
- final equity = final equity-curve point;
- evaluation decision-cycle count = actual decision-cycle count;
- fees paid = all virtual-lot entry fees + all closed-lot exit fees.

Step 7 already validates the detailed local-authorized / not-reserved / Master-admit / Master-reject /
PAPER-executed / cash-blocked accounting. Step 8 re-hashes that evaluation and seals its fingerprint.

## Authority boundary

The audit rejects any replay artifact that unexpectedly exposes Risk, Master admission or LIVE
authority.

Expected PAPER broker authority inside Step 5/6 execution artifacts remains bounded to their existing
historical PAPER responsibilities. Step 8 itself has no broker authority and never invokes those
services.

The Step 8 report and seal explicitly expose:

- `audit_only = True`;
- `mutation_applied = False`;
- `reservation_mutation = False`;
- `broker_called = False`;
- `risk_authority = False`;
- `admission_authority = False`;
- `registry_mutation = False`;
- `live_authority = False`;
- `auto_execute = False`.

The closure seal additionally exposes no local-Risk override or resize authority.

## Determinism

`sealed_at` is the exact final historical timeline barrier timestamp, not wall-clock time. Re-auditing
an identical replay therefore produces the same audit and closure fingerprints.

The APIs are:

- `audit_master_historical_coordinated_replay()`;
- `seal_master_historical_coordinated_replay()`.

## Batch 21e closure boundary

After Step 8, Batch 21e has a complete deterministic PAPER historical path and a dedicated audit seal
covering the replay state graph.

Exact AI Gateway usage and economic-net accounting remain intentionally outside this closure because
Step 7 marks AI cost evidence `UNAVAILABLE` when it is not supplied. Step 8 verifies rather than
fabricates that boundary.

Step 8 does not add dynamic allocation, Kelly sizing, statistical correlation, automatic promotion,
Task Force authority or LIVE readiness.

The next architectural batch can therefore begin from a sealed Batch 21e baseline and remain advisory
until explicitly connected through existing authority gates.

## Validation in generation harness

- Step 8 targeted tests: 25 passed;
- reconstructed `tests/portfolio`: 561 passed;
- Python compilation: passed;
- Python source/test line length <= 100: passed.

Run Ruff, targeted Step 8 tests, all Portfolio tests and the complete repository suite in the real
checkout before commit.
