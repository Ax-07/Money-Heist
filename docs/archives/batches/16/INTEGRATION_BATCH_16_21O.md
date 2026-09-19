# Batch 16.21o — Historical Denver Wiring

## Objective

Wire one explicitly supplied, already-frozen Denver prior into historical replay
without allowing the replay to mutate or rebuild that prior.

This batch does not add Dashboard prior upload yet. It establishes the runner
contract that the future operator/runtime activation must use.

## One frozen source, two consumers

At an opportunity boundary:

```text
FrozenDenverPriorCatalog
          ↓
FrozenDenverPriorContextProvider
          ↓
one validated DenverContext
          ├── DecisionContext.statistics.denver_context
          └── specialist_contexts["denver"]
```

The exact same validated `DenverContext` object is attached to both paths.

Denver is not advertised when the frozen prior has no statistics for the
current setup.

## Temporal contract

The frozen provider now anchors `DenverContext.as_of` to `prior.cutoff`, not to
the current market clock.

Therefore a prior frozen at time T remains the same historical evidence at
T+1, T+100, and in later LIVE decisions.

The runner requires:

`prior.cutoff <= run.period_start`

and, when `denver_formal_oos=True`, the prior policy must be:

`STRICT_PRE_OOS`

This prevents a prior frozen at the start of OOS from being injected backwards
into DESIGN or VALIDATION.

## Reproducibility binding

The prior assumptions bind:

- `denver_context_binding_version=frozen-denver-decision-context-v1`;
- prior version;
- prior ID;
- prior policy;
- prior cutoff;
- inner catalog ID;
- setup definition version;
- observation count;
- source strategy fingerprint.

The replay additionally binds:

- `denver_formal_oos=true|false`.

Any mismatch fails closed before historical decisions are executed.

## DecisionContext.statistics

When a matching setup exists, `statistics` is AVAILABLE and contains:

- prior version;
- prior ID;
- prior policy;
- prior cutoff;
- the exact validated `DenverContext`.

Statistics provenance is:

- source: `frozen_denver_prior`;
- observed/available time: the frozen prior cutoff;
- source fingerprint: the content-addressed prior fingerprint;
- quality: Denver's deterministic sample-size band;
- missing fields: statistical metrics unavailable in the frozen context.

When no matching setup exists, `statistics` remains UNAVAILABLE and Denver is
not included in specialist contexts.

## Rio coexistence

Rio and Denver can coexist on the same historical decision:

```text
specialist_contexts = {
    "rio": exact frozen RioContext,
    "denver": exact frozen DenverContext,
}
```

Neither specialist changes Scanner cadence, PAPER execution, Risk Engine state,
or broker authority.

## Safety invariants

- no prior mutation during replay;
- no OOS self-learning;
- no automatic catalog building inside a decision;
- no future observations admitted after the prior cutoff;
- no arbitrary setup attribution;
- no Denver without full MTF DecisionContext parity;
- Risk Engine remains authoritative.

## Validation

```powershell
uv run pytest -q tests/backtest/test_denver_prior.py
uv run pytest -q tests/backtest/test_replay_runner_mtf.py
uv run pytest -q
```

The next batch can add explicit Dashboard/Ablation loading of a frozen prior
without changing this runner contract.
