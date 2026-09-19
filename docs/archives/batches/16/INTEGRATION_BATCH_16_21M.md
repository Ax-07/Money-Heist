# Batch 16.21m — Frozen Denver Prior Catalog

## Objective

Create the immutable historical-prior artifact that Denver must consume before
Denver is activated in normal historical replay or LIVE.

The existing `HistoricalSetupStatsCatalog` is already cutoff-safe when queried:
only trades with `closed_at <= as_of` are counted.

That is necessary but not sufficient for formal OOS evaluation. A mutable or
progressively rebuilt catalog could still learn from earlier trades inside the
same OOS period.

Batch 16.21m therefore adds a second boundary: a **frozen prior artifact**.

## Version

`frozen-denver-prior-v1`

## Policies

### STRICT_PRE_OOS

Intended for formal OOS evaluation.

At freeze time:

- only observations closed on or before the cutoff are eligible;
- OOS-labelled observations are excluded;
- DESIGN and VALIDATION observations may be retained;
- the resulting prior may only be used when its cutoff is no later than the
  target period start.

Formal OOS requires this policy.

### ALL_CLOSED_BEFORE_CUTOFF

Intended for forward/live use after historical evaluation has completed.

Any historical DESIGN / VALIDATION / OOS observation may be retained if it was
already closed by the cutoff.

This policy is deliberately rejected for formal OOS activation.

## Reproducibility

The prior is content addressed and binds:

- prior version;
- prior ID;
- policy;
- cutoff;
- inner Denver setup-stats catalog ID;
- setup-definition version;
- observation count;
- source strategy fingerprint.

Changing one observation, PnL, close time, source role, cutoff or policy changes
the artifact identity.

## Provider behavior

`FrozenDenverPriorContextProvider` is read-only.

It refuses:

- a target period that starts before the prior cutoff;
- a formal OOS target using a non-strict policy;
- BacktestConfig assumptions that do not bind the exact prior;
- a market observation earlier than the prior cutoff.

For a matching setup, Denver receives statistics calculated only from the
already-frozen observations plus explicit prior provenance in `notes`.

No OOS trade executed after the freeze can enter the context.

## Deliberate non-goals

16.21m does not activate Denver in the replay runtime yet.

It does not build a prior automatically from the campaign currently being
tested.

It does not allow the OOS run to mutate its own historical prior.

The next batch will wire one explicitly supplied frozen prior into the same
decision boundary used by `DecisionContext.statistics` and Denver.

## Commands

```powershell
uv run pytest -q tests/backtest/test_denver_prior.py
uv run pytest -q
```

Given an existing setup-stats catalog:

```powershell
uv run python .\scripts\freeze_denver_prior.py `
  ".\path\to\denver_setup_stats_catalog.json" `
  ".\path\to\denver_prior.json" `
  --cutoff "2026-01-01T00:00:00Z" `
  --policy STRICT_PRE_OOS
```

Validation:

```powershell
uv run python .\scripts\validate_frozen_denver_prior.py `
  ".\path\to\denver_prior.json" `
  --target-start "2026-01-01T00:00:00Z" `
  --formal-oos
```
