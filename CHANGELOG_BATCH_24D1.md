# Money Heist — Changelog Batch 24D.1

## Decision Quality Research Foundation & Outcome Join

Baseline : `a010155337a446bcbd06ded32667ea667b1512d7`.

Ajouts :
- namespace `app.evaluation.decision_quality` ;
- `CandidateResearchRecord` et `ScannerResearchRecord` séparés ;
- blocs `causal` et `posthoc` explicites ;
- `DecisionQualityResearchRun` et `DecisionQualityResearchBundle` déterministes ;
- jointures exactes `opportunity_id` et `scanner_evaluation_id == scan_id` ;
- conservation des horizons incomplets 23A sans métrique partielle ;
- coverage diagnostics pour outcomes, Decision Intelligence et Analytics manquants ;
- erreurs fail-closed sur contamination run/role/dataset/identity ;
- support `NO_TRIGGER`, `TRIGGER_BELOW_CANDIDATE_THRESHOLD`, `CANDIDATE_OPPORTUNITY` ;
- tests de déterminisme, causal-fingerprint independence, isolation business et architecture.

Non modifié : Scanner, DecisionContext, prompts/agents, Palermo, Risk, PAPER, LIVE,
Forward Outcome engines, seuils, sizing, business identity et `BacktestRun.run_id`.

Aucune persistance frontend ou auto-tuning ajouté dans 24D.1.
