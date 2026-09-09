# Batch 18a — Réputation et ablation — clôture des fondations

## État

Steps 1 à 4 livrés et conçus comme une couche d’évaluation déterministe/advisory-only.

## Step 1 — Fondations réputation + ablation

- comparaison stricte baseline vs run sans exactement un agent ;
- comparabilité par fingerprint expérimental, dataset, rôle, période, bougies et opportunités ;
- deltas Trading Net / Economic Net / drawdown / coût IA ;
- agrégation d’ablation ;
- `AgentReputationProfile` multidimensionnel ;
- aucune mutation runtime.

## Step 2 — Policy de recommandation d’état

- `AgentStateEvidence` ;
- seuils explicites `ReputationPolicyThresholds` ;
- recommandations `HOLD / PROMOTE / DEMOTE / REDUCE_FREQUENCY` ;
- transitions progressives ;
- fonctions Core protégées ;
- `auto_apply=False`.

## Step 3 — Bridge et rapport auditable

- `ReputationAdvisoryService` ;
- adaptation Step 1 → Step 2 ;
- ablation OOS-only pour la preuve de transition ;
- contrôle du scope de coût IA ;
- provenance runs/datasets/fingerprints ;
- `AgentReputationAdvisoryReport` avec fingerprint SHA-256 déterministe.

## Step 4 — API publique, exports et documentation

- consolidation des exports publics dans `app/evaluation/__init__.py` ;
- `reputation_advisory_to_dict()` / `reputation_advisory_to_json()` ;
- sérialisation JSON-safe des Decimal/enums/dataclasses sans mutation ;
- updater documentaire idempotent pour Evaluation/API/Roadmap ;
- tests d’API publique, d’exports et de préservation documentaire.

## Frontières

Batch 18a ne :
- modifie pas automatiquement `AgentRegistry` ;
- ne fixe pas de seuil de production ;
- n’active pas le LIVE ;
- ne modifie pas le Risk Engine ni le broker ;
- ne considère pas l’ablation comme une preuve causale universelle ;
- ne transforme pas DESIGN/VALIDATION en OOS.

Les campagnes empiriques comparables et les critères opérateur pré-définis restent nécessaires avant
toute décision organisationnelle réelle sur un agent.

<!-- BATCH18B_STEP4_CHANGELOG_START -->

# Batch 18b — Ablation Campaign Runner — clôture

## Livré

- plan de campagne déterministe baseline + `WITHOUT_AGENT` ;
- `run_id` distinct par twin avec fingerprint de comparaison commun ;
- exécution Batch 16/PAPER isolée par variant ;
- conversion automatique en `BacktestPeriodReport` et `AblationComparison` ;
- rejet de toute réutilisation broker/runner entre twins ;
- PAPER Runtime Factory dans `app.services.backtest`, hors couche Evaluation ;
- spécialistes recréés avec un AI Gateway/budget/usage scope propre à chaque variant ;
- modes IA MOCK/CACHED/LIVE_EVAL conservés ;
- export compact JSON/dict du rapport de campagne ;
- exports publics lazy pour éviter les cycles Evaluation ↔ Backtest ;
- aucune mutation `AgentRegistry`, aucun bypass Risk et aucun trading LIVE.

## Clôture Batch 18

Batch 18a + 18b fournissent désormais l'infrastructure complète de réputation et d'ablation.
Une décision organisationnelle réelle reste conditionnée aux campagnes empiriques,
à l'OOS et aux
seuils opérateur pré-définis ; elle n'est jamais appliquée automatiquement.

<!-- BATCH18B_STEP4_CHANGELOG_END -->
