# Batch 24A.1 — Analytics Lab Foundation, Contracts & Isolation Guards

**Baseline :** `main @ 55a5333941ffc043b26b5e30f4b9fdafbd1cf8b0`
**Statut :** implémentation à valider localement

## Objectif

Poser les contrats déterministes et les garde-fous d'isolation du futur Analytics Lab, sans ajouter d'indicateur, Technical Event, ZigZag, Pattern, Context/Sequence, attribution ou UI Analytics.

## Composants ajoutés

```text
app/common/canonical.py
app/analytics/__init__.py
app/analytics/ids.py
app/analytics/models.py
app/analytics/provenance.py
app/analytics/manifest.py
app/services/backtest/analytics_lab.py
```

Contrats principaux :
- `AnalyticsComponentVersions` ;
- `AnalyticsAsOfInput` ;
- `AnalyticsLabRun` ;
- `AnalyticsSnapshot` ;
- `AnalyticsLabManifest` ;
- `AnalyticsObservationProvenance`.

## Identité

`AnalyticsLabRun.create()` calcule une identité à partir de la provenance descriptive : source backtest, dataset hash, système, symbol/timeframes, bornes et rôle de période, politique MTF et versions Analytics.

Aucun outcome futur ni résultat de décision postérieur n'entre dans cette identité.

`AnalyticsSnapshot.create()` lie un snapshot à l'univers visible exact via `source_cursor_fingerprint`. En 24A.1, `components={}` est un snapshot valide.

`build_analytics_manifest()` trie les snapshots de manière déterministe et calcule `analytics_sha256` via la canonicalisation Money Heist.

## Non-régression

Le Batch 24A.1 ne modifie pas :
- `CandidateOpportunity` ;
- `DecisionContextV1` ;
- Scanner ;
- agents / Professor / Palermo ;
- Risk Engine ;
- PaperBroker ;
- LIVE ;
- `BacktestConfig`.

Une modification de `analytics_bundle_version` ou d'une version de composant produit une nouvelle identité Analytics tout en conservant le même `BacktestRun.run_id`.

## Validation

```powershell
cd "E:\0 money heist"
uv sync
uv run pytest -q tests/analytics
uv run pytest -q
uv run ruff check app tests
```

Le batch ne doit pas être considéré clos avant validation de la suite locale complète.
