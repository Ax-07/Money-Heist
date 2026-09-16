# Batch 23A.1 — Decision Funnel Baseline

Baseline d'origine : `v0.1.0` / `0f0b53082e24919e6cb154436118b5e300d42646`.

## Objectif

Ajouter une couche de mesure causale du pipeline sans modifier les décisions de trading.

Le rapport est construit après Historical Replay à partir des sorties déjà produites : `ScanResult`, `CandidateOpportunity`, `OrchestrationResult`, `ComputeGateDecision`, `ProfessorFinalDecision`, `TradeProposal`, `RiskDecision`, ordre/fill PAPER et Evaluation.

## Frontière causale

Le Decision Funnel n'entre jamais dans `DecisionContext`. Les données postérieures au choix, notamment `closed_trades`, sont placées dans `post_hoc`.

## Instrumentation ajoutée au runner

Deux compteurs uniquement :

- `pre_scanner_warmup_skipped` ;
- `pre_scanner_not_decision_close_skipped`.

Aucune règle Scanner, Compute Gate, Professor, agent, Risk ou exécution n'est modifiée.

## Invariants

- `candles_evaluated = pre_scanner_skips + scanner_evaluations` ;
- `scanner_evaluations = scanner_no_trigger + scanner_triggered` ;
- le rapport est déterministe et les reason codes sont triés ;
- le `business_sha256` historique ne dépend pas des nouveaux compteurs d'observation.

## Persistance

Le Backtest Dashboard expose le rapport dans chaque `PeriodSummary` et ajoute les exports :

- `design-decision-funnel.json` ;
- `validation-decision-funnel.json` ;
- `oos-decision-funnel.json`.

Les anciens `summary.json` restent lisibles grâce au champ optionnel `decision_funnel`.
