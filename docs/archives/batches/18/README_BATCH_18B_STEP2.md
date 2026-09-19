# Money Heist — Batch 18b Step 2 — Ablation Campaign Execution

## Objectif

Exécuter un `AblationCampaignPlan` du Step 1 en réutilisant les primitives Batch 16 :

- un `HistoricalReplayRunner` isolé par variant ;
- un broker PAPER isolé par variant ;
- `evaluate_historical_replay()` pour l'évaluation Batch 10/16 ;
- `BacktestPeriodReport.from_evaluation()` pour la normalisation ;
- `compare_ablation()` du Batch 18a pour les deltas marginaux.

## Flux

```text
AblationCampaignPlan
  -> BASELINE runtime PAPER isolé
  -> WITHOUT_AGENT runtimes PAPER isolés
  -> HistoricalReplayRunner.run(...)
  -> evaluate_historical_replay(...)
  -> BacktestPeriodReport
  -> compare_ablation(...)
  -> AblationCampaignExecutionReport
```

## Isolation

Le `runtime_factory` doit construire un runtime neuf pour chaque variant. Le Step 2 rejette
explicitement la réutilisation du même runner ou du même broker entre deux variants afin d'éviter
les fuites d'état : positions, balance, journal, budget IA, usage IA ou horloge de replay.

Le mapping de spécialistes reçu par le factory est déjà filtré par
`build_variant_specialists()` du Step 1. Le registry global n'est jamais muté.

## OOS

Le runner accepte DESIGN, VALIDATION ou OOS via `BacktestPeriodRole`. Une campagne OOS produit des
`AblationComparison.is_out_of_sample=True`, compatibles avec le bridge advisory du Batch 18a.
DESIGN/VALIDATION ne sont jamais requalifiés en OOS.

## Frontières

- PAPER/historical replay uniquement ;
- aucune mutation `AgentRegistry` ;
- aucun changement Risk Engine ;
- aucun broker LIVE ;
- aucune promotion automatique ;
- aucun seuil de réputation inventé.

## Validation

```powershell
uv run pytest -q tests/evaluation/test_ablation_campaign_execution.py
uv run pytest -q
```
