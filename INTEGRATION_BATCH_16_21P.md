# Batch 16.21p — Frozen Denver Runtime Activation

This batch activates an already-frozen Denver prior explicitly in the Backtest
Dashboard and PAPER ablation runtime.

Activation remains OFF by default.

## OOS_ONLY

Recommended for formal OOS:

- requires `STRICT_PRE_OOS`;
- DESIGN and VALIDATION receive no prior;
- only OOS receives the exact frozen prior;
- `denver_formal_oos=True`.

## ALL_PERIODS

For a prior frozen before the entire target dataset:

- the same exact prior is injected into each period;
- `denver_formal_oos=False`;
- the runner still enforces `prior.cutoff <= run.period_start`.

## Runtime binding

Execution assumptions bind runtime version, activation mode, formal-OOS flag,
and every immutable prior identity field.

## Dashboard

Adds an explicit prior JSON upload and activation selector. No file is
auto-discovered and the current campaign's generated catalog is never fed back
automatically.

## Ablation

`PaperAblationRuntimeSettings` accepts the exact prior and an explicit period
role. `OOS_ONLY` refuses role-less activation rather than guessing.

## Safety invariants

- no implicit activation by file presence;
- no current-campaign self-learning;
- no DESIGN/VALIDATION contamination in `OOS_ONLY`;
- no role guessing in ablation;
- no non-MTF Denver activation;
- no symbol/system/timeframe drift;
- Risk Engine remains authoritative.

## Validation

```powershell
uv run pytest -q tests/backtest/test_denver_runtime_activation.py
uv run pytest -q tests/dashboard/test_denver_runtime_activation.py
uv run pytest -q tests/evaluation/test_ablation_campaign_runtime.py
uv run pytest -q tests/backtest/test_denver_prior.py
uv run pytest -q tests/backtest/test_replay_runner_mtf.py
uv run pytest -q
```
