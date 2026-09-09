# Money Heist — Batch 18b Step 1 — Ablation Campaign Planning

## Objectif

Construire une campagne d'ablation reproductible avant toute exécution : une baseline et un twin
`WITHOUT_AGENT` pour chaque spécialiste ciblé, sans mutation du registry global.

## Contrat

```text
BacktestRun source + crew de spécialistes + cibles
→ AblationCampaignPlan
  → BASELINE
  → WITHOUT_AGENT(berlin)
  → WITHOUT_AGENT(tokyo)
  → ...
```

Chaque variant possède :

- un `variant_id` déterministe ;
- un `BacktestRun.run_id` propre ;
- le même `comparison_fingerprint` de campagne ;
- la liste exacte des spécialistes inclus ;
- une provenance dans `BacktestConfig.execution_assumptions` ;
- le même dataset, la même période et les mêmes paramètres de replay que le run source.

Le module fournit aussi `build_variant_specialists()`. Il construit un nouveau mapping à injecter dans
`OrchestrationPipeline(specialists=...)` et retire exactement le spécialiste ablaté. Le mapping source
n'est jamais modifié.

Après exécution d'un variant, `AblationCampaignVariant.to_descriptor(report)` construit directement
le `AblationRunDescriptor` Batch 18a en vérifiant run, dataset et bornes temporelles.

## Frontières

- aucune exécution de replay dans ce Step 1 ;
- aucune mutation de `AgentRegistry` ;
- aucun seuil de réputation ;
- aucune modification Risk Engine / broker / LIVE ;
- aucune donnée future ;
- les métadonnées d'ablation servent uniquement à l'identité/audit de l'expérience.

## Validation

```powershell
uv run pytest -q tests/evaluation/test_ablation_campaign.py
uv run pytest -q
```
