# Batch 24A.5 — Patterns & Causal Lifecycle

## Statut

Implémentation Analytics expérimentale, read-only, observation-only, sans autorité de trading.

## Baseline

`2056b95810c01f15bad3f8c29c218a5c7d8fd009` — `feat(analytics): add causal structure and zigzag`.

## Référence conceptuelle

Le registry et la géométrie sont adaptés du moteur `btc_analytics_v1` P5.v2. Les seuils géométriques sont conservés, mais le détecteur de pivots P5.v2 n'est pas porté : la source primaire est `CAUSAL_ZIGZAG` via `PatternPivot`.

## Catalogue

- DOUBLE_TOP / DOUBLE_BOTTOM
- HEAD_AND_SHOULDERS / INVERSE_HEAD_AND_SHOULDERS
- ASCENDING_TRIANGLE / DESCENDING_TRIANGLE / SYMMETRICAL_TRIANGLE
- RISING_WEDGE / FALLING_WEDGE
- ASCENDING_CHANNEL / DESCENDING_CHANNEL
- RANGE

Tous sont `experimental=true`.

## Lifecycle causal

États : `FORMING`, `CONFIRMED`, `FAILED`, `INVALIDATED`.

`detected_at` est le premier instant où tous les pivots requis sont confirmés. `CONFIRMED` est produit par un breakout sur clôture au-delà du niveau/segment et du buffer ATR. `FAILED` correspond à l'échec technique avant confirmation (structure cassée, bornes croisées ou timeout). `INVALIDATED` est réservé à une occurrence déjà confirmée qui réintègre ensuite sa structure selon la règle versionnée.

Aucun outcome, P&L, MFE, MAE ou Forward Outcome ne participe à ces transitions.

## Causalité

Pour `as_of=T` :

- seules les candles closes avec `close_time <= T` sont visibles ;
- seuls les pivots avec `confirmed_at <= T` sont visibles ;
- aucune transition dont `available_at > T` ne peut être publiée ;
- l'identité `pattern_id` reste stable ;
- le `pattern_fingerprint` évolue lorsque l'état visible évolue ;
- la direction des géométries reste `NEUTRAL` avant un breakout causal ;
- le cursor fingerprint d'occurrence est ancré au dernier pivot requis à la détection.

Exemple : géométrie T1, dernier pivot confirmé T7, breakout T10, invalidation T15 : T6 absent, T8 FORMING, T11 CONFIRMED, T15 INVALIDATED.

## Same-candle ambiguity

Policy `money-heist.pattern-intrabar-conservative.v1` : la confirmation et l'invalidation sont fondées sur la clôture de candle. Un high/low intrabar, seul, ne peut donc ni confirmer ni invalider un pattern. L'ordre `high -> low` ou `low -> high` n'est jamais inventé. Les timeouts deviennent disponibles à la clôture exacte de leur dernier bar autorisé, sans attendre une candle future.

## Identité Analytics

`pattern_registry_version` est inclus dans `AnalyticsComponentVersions`; l'installation de ce registry modifie donc l'identité Analytics mais ne modifie ni `BacktestRun.run_id` ni le business fingerprint.

## Frontières

`app.analytics.patterns` n'importe pas Scanner, DecisionContext, agents, Risk, PAPER/LIVE ni Forward Outcomes. Le chemin décisionnel n'importe pas `app.analytics.patterns`.

## Hors scope

Pas de calibration 24A.6, pas de comparaison de sources, pas de contexte/séquences 24A.7, pas d'attribution 24B, pas d'UI 24C et pas de recherche de qualité 24D.
