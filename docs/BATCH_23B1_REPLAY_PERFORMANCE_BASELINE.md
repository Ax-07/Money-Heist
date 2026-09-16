# Batch 23B.1 — Historical Replay Performance Baseline

<!-- BATCH23B1_REPLAY_PERFORMANCE_BASELINE -->

**Baseline :** `4368a99944eb04ba3b53cc31f6b379041aa3cbf3`  
**Type :** optimisation non métier + observabilité + UX opérateur

## Objectif

Réduire le coût temporel des campagnes historiques longues sans modifier Scanner, Feature Engine, agents, Professor, Palermo, Risk Engine, broker, splits ou logique 23A.

## Livré

- pool HTTP OpenAI persistant au niveau de chaque run historique, fermé explicitement même en cas d'annulation/erreur ;
- profil wall-clock additif dans `HistoricalReplayResult` : lifecycle, MTF/features/Scanner, construction du contexte, pipeline ;
- profil par période dans `PeriodSummary.performance` : replay, évaluation, couche de mesure 23A et latence fournisseur IA cumulative ;
- exports `design-performance.json`, `validation-performance.json`, `oos-performance.json` ;
- métriques live de progression : temps écoulé, nombre d'appels IA, temps IA cumulé ;
- endpoint V2 `POST /api/frontend/v2/backtests/runs/{campaign_id}/cancel` ;
- bouton **Annuler le backtest** dans le Frontend V2 ;
- panneau **Performance du replay** après campagne.

## Frontière causale

Les timings sont observationnels et non déterministes. Ils ne sont jamais injectés dans `DecisionContext`, ne changent aucun `run_id`/fingerprint métier et ne doivent pas être utilisés comme entrée de décision.

## Important

`ai_provider_latency_ms` et `ai_wall_time_ms` sont cumulatifs par requête. Comme les spécialistes peuvent s'exécuter en parallèle, cette somme peut dépasser le temps mur de la période. Elle sert à mesurer la charge fournisseur, pas à calculer directement une part de temps exclusif.

## Suite

Après une campagne réelle 1m → décision 1h, comparer les profils DESIGN / VALIDATION / OOS. Les optimisations structurelles suivantes (checkpoint de split, Feature Engine incrémental, fast-path lifecycle) ne seront engagées qu'à partir de ces mesures et devront prouver une parité fonctionnelle stricte avant/après.
