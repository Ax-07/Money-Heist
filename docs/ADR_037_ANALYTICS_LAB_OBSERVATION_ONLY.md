# ADR-037 — Analytics Lab Observation-Only Authority Boundary

**Date :** 2026-09-16
**Statut :** ACCEPTED
**Batch :** 24A.1 — Analytics Lab Foundation, Contracts & Isolation Guards
**Baseline :** `55a5333941ffc043b26b5e30f4b9fdafbd1cf8b0`

## Décision

Le package `app.analytics` constitue une couche **READ-ONLY / OBSERVATION-ONLY / DETERMINISTIC / CAUSAL / REPLAY-SAFE**. Il n'a aucune autorité de trading et ne participe pas au chemin comportemental Money Heist pendant les Batchs 24A–24D.

L'Analytics Lab dérive exclusivement des données et identités déjà canoniques de Money Heist : `DatasetRef`, Historical Replay et `HistoricalMultiTimeframeCursor`. Il ne possède aucun provider de marché, downloader, parser CSV autonome, gap filling, candle synthétique ni resampler MTF indépendant.

`BacktestRun` et `AnalyticsLabRun` sont deux identités distinctes. Tant que l'Analytics Lab reste observation-only, ses versions ne participent ni à `BacktestConfig`, ni au `BacktestRun.run_id`, ni au business fingerprint du backtest.

Les Forward Outcomes Batch 23A restent la seule vérité post-hoc sur le futur. `app.analytics` ne dépend pas des modules Forward Outcomes, Scanner Forward Outcomes ou Funnel Outcome Attribution. Une attribution future réunissant décision, Analytics et outcomes devra vivre dans un composant séparé.

## Frontière d'autorité

Interdits pendant 24A–24D :

```text
Analytics X→ Scanner
Analytics X→ CandidateOpportunity creation
Analytics X→ Compute Gate
Analytics X→ DecisionContextV1
Analytics X→ Professor / Specialists / Palermo
Analytics X→ TradeProposal
Analytics X→ Risk Engine
Analytics X→ Paper Broker
Analytics X→ LIVE
```

Des tests AST imposent notamment :
- aucun import `app.analytics` depuis le chemin décisionnel ;
- aucun import Forward Outcomes depuis `app.analytics` ;
- aucun import LIVE depuis `app.analytics`.

## Provenance et causalité

Chaque observation Analytics doit pouvoir être reliée à :
- `source_backtest_run_id` ;
- identité/version/hash du dataset ;
- `as_of` timezone-aware ;
- source/decision timeframe ;
- `mtf_policy_version` ;
- `source_cursor_fingerprint` ;
- versions Analytics.

Les futures observations distinguent `event_at` de `available_at` et doivent satisfaire `event_at <= available_at <= as_of`.

## DESIGN / VALIDATION / OOS

Chaque `AnalyticsLabRun` conserve explicitement un rôle `DESIGN`, `VALIDATION` ou `OOS`. Les périodes ne sont jamais fusionnées silencieusement.

## Canonicalisation

La canonicalisation Money Heist est factorisée sans changement sémantique dans `app.common.canonical`. L'API historique `app.services.backtest.ids` est conservée et un test golden verrouille les sorties JSON/SHA-256/UUID existantes afin d'empêcher une dérive rétroactive des fingerprints.

## Frontière comportementale future

Si un futur batch injecte des données Analytics dans `DecisionContextV1` ou dans tout composant influençant Scanner/agents/Risk/exécution, cette intégration devient **comportementale**. Les versions Analytics concernées devront alors participer aux identités de configuration/replay/prompt/fingerprint appropriées. Cette intégration n'est pas autorisée par 24A.1.
