# Integration — Batch 24A.3 Technical Events

Baseline required and audited: `98f1ffc01590eef8351d1110a4354d07355c5d86` on `main`.

Reference audit: `Ax-07/btc_analytics_v1@07e9af22d8f5cc509d9a8dd50a2e7451249295c1`,
Technical Event registry `p4.v1`.

## 1. Vérifier la baseline

```powershell
git fetch origin
git checkout main
git pull --ff-only origin main
git rev-parse HEAD
```

Le SHA attendu pour ce lot est :

```text
98f1ffc01590eef8351d1110a4354d07355c5d86
```

Si `main` a avancé, auditer les commits supplémentaires avant d’appliquer l’overlay.

## 2. Copier l’overlay

Extraire/copier le contenu du ZIP à la racine du repository en conservant les chemins.
Le lot crée `app/analytics/events/**`, `tests/analytics/events/**`, la documentation dédiée
et les fichiers d’intégration. `tests/analytics/events/__init__.py` namespace les tests 24A.3
afin d’éviter les collisions de noms de modules avec `tests/analytics/indicators/**`.
Le lot ne remplace aucun fichier Scanner/Feature/Decision/Risk.

## 3. Appliquer les notes documentaires consolidées

```powershell
uv run python apply_batch_24a3_docs.py
```

Le script est idempotent et ajoute uniquement les sections 24A.3 aux documents concernés.

## 4. Tests ciblés

```powershell
uv run pytest tests/analytics/events -q
uv run pytest tests/analytics/indicators -q
uv run pytest tests/analytics -q
```

## 5. Non-régression complète

```powershell
uv run pytest -q
```

## 6. Qualité

```powershell
uv run ruff check app/analytics/events tests/analytics/events apply_batch_24a3_docs.py
uv run ruff format --check app/analytics/events tests/analytics/events apply_batch_24a3_docs.py
git diff --check
```

## 7. Contrôles d’isolation à inspecter

Le diff ne doit contenir aucune modification fonctionnelle sous :

```text
app/market/features/**
app/market/scanner/**
app/services/decision_context/**
app/agents/**
app/services/orchestration/**
app/trading/risk/**
app/trading/paper/**
app/trading/live/**
app/services/backtest/models.py
app/services/backtest/reproducibility.py
```

`app.analytics.events` ne doit importer ni Scanner, ni Agents, ni Decision Context, ni
Forward Outcomes, ni trading. Les business paths ne doivent pas importer
`app.analytics.events`.

## 8. Points fonctionnels à vérifier

- 35 event types uniques et tous adossés au registry Indicators 24A.2 ;
- seuils centralisés : RSI 30/50/70, ADX 25, MFI 20/80, volume ratio 1.5 ;
- equality/crossover semantics déterministes ;
- aucun événement répété tant qu’un état persiste ;
- warmup/missing values => aucun événement ;
- ordre des événements = ordre du registry ;
- same inputs => same IDs/fingerprints ;
- `available_at <= AnalyticsSnapshot.as_of` ;
- prefix invariance et future malformed candle isolation ;
- incomplete higher timeframe => aucun événement ;
- event registry version modifie l’identité Analytics, pas le source `BacktestRun` ;
- aucune autorité LONG/SHORT/trading.

## 9. Commit recommandé après validation

```powershell
git status --short
git diff --stat
git diff --check
git add app/analytics/events tests/analytics/events `
  docs/BATCH_24A3_TECHNICAL_EVENTS.md docs/02_ARCHITECTURE.md `
  docs/08_API_ET_MODELES_DE_DONNEES.md docs/09_ROADMAP_DEVELOPPEMENT.md `
  docs/10_DECISIONS_ET_CHANGELOG.md docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md `
  docs/ANALYTICS_INDICATOR_PARITY.md CHANGELOG_BATCH.md apply_batch_24a3_docs.py `
  INTEGRATION_BATCH_24A3.md MANIFEST_BATCH_24A3.txt SHA256SUMS_BATCH_24A3.txt
git commit -m "feat(analytics): add Batch 24A.3 technical events"
git push origin main
```

Ne pousser qu’après réussite des tests ciblés, de la suite complète et des contrôles de diff.
