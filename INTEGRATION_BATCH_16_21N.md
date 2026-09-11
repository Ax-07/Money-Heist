# Batch 16.21n — Denver Catalog Export

## Objective

Make the existing deterministic Denver statistics pipeline operational from the
normal Backtest Dashboard by exporting a real setup-stats catalog after each
completed DESIGN / VALIDATION / OOS split.

This batch does **not** activate Denver in decision making.

It only creates the historical artifact that can later be frozen by Batch
16.21m and then supplied to Denver.

## Source of truth

The export is built directly from the in-memory objects already produced by the
real backtest:

```text
DESIGN replay + evaluation
VALIDATION replay + evaluation
OOS replay + evaluation
            ↓
catalog_from_historical_runs(...)
            ↓
denver-setup-stats-catalog.json
```

No CSV trade re-parsing or heuristic setup reconstruction is introduced.

`observations_from_historical_replay(...)` remains responsible for strict
attribution between each closed trade and exactly one executed opportunity /
setup.

Ambiguous attribution therefore remains fail-closed.

## Preserved role provenance

Each observation keeps its original:

- `DESIGN`;
- `VALIDATION`;
- `OOS`.

That is important because the next `freeze_denver_prior.py` step can apply:

`STRICT_PRE_OOS`

and remove every OOS observation while also enforcing the requested temporal
cutoff.

## Dashboard export

Every completed split now includes:

`denver-setup-stats-catalog.json`

in the existing `CampaignSummary.exports` collection.

The existing generic export endpoint serves it without adding a new route.

## Empty catalogs

A technically valid campaign with zero attributable closed trades still exports
a valid empty setup-stats catalog.

That artifact cannot be frozen into a Denver prior because Batch 16.21m
requires at least one eligible observation.

This is intentional.

## Workflow

After a sufficiently large historical campaign:

1. download `denver-setup-stats-catalog.json`;
2. validate it;
3. freeze it at the desired cutoff;
4. validate the frozen prior;
5. only then wire that frozen prior into Denver.

Example:

```powershell
uv run python .\scripts\validate_denver_setup_stats_catalog.py `
  ".\data\historical\denver\denver-setup-stats-catalog.json"

uv run python .\scripts\freeze_denver_prior.py `
  ".\data\historical\denver\denver-setup-stats-catalog.json" `
  ".\data\historical\denver\denver-prior-oos.json" `
  --cutoff "<OOS_START_UTC>" `
  --policy STRICT_PRE_OOS
```

## Validation

```powershell
uv run pytest -q tests/dashboard/test_backtest_dashboard.py
uv run pytest -q
```


## Ambiguous attribution policy

A Denver catalog is an auxiliary statistical artifact. It must never make the
underlying trading campaign invalid.

If one closed trade cannot be mapped to exactly one executed setup (for example
because a position was scaled or combined), `observations_from_historical_replay`
raises the dedicated `HistoricalSetupAttributionError`.

The Dashboard catches only this specific attribution error:

- the campaign remains `COMPLETED`;
- no `denver-setup-stats-catalog.json` is exported;
- `denver-setup-stats-status.json` is exported with
  `status=UNAVAILABLE` and `reason=AMBIGUOUS_TRADE_ATTRIBUTION`.

Unexpected catalog-building errors are still allowed to fail the campaign.

This preserves the scientific invariant: ambiguous trades are never assigned
heuristically to a Denver setup.
