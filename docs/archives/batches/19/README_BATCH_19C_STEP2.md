# Batch 19c — Step 2 — Batch 18 Reputation + Candidate Costs

Baseline attendue : Batch 19c Step 1 installé et validé localement.

## Objectif

Construire un rapport d'évidence candidat à partir de :

- la campagne Recruitment exécutée ;
- son `RecruitmentEvidenceGateDecision` ;
- son bridge validé vers `AblationComparison` Batch 18 ;
- les `AgentMetrics` Batch 10 du candidat ;
- l'agrégation d'ablation et les dimensions de réputation Batch 18.

Ce step ne compare pas encore les success criteria et ne produit aucune recommandation de lifecycle/promotion.

## Réutilisation Batch 18

Le code réutilise :

- `aggregate_ablation(...)` ;
- `build_agent_reputation(...)`.

Le profil Batch 18 n'est utilisé que pour normaliser les dimensions réputationnelles : participation, accord directionnel, confiance, coût/latence moyens, contribution marginale trading/économique et effet drawdown.

Les champs Batch 18 orientés `AgentState` ne sont pas exposés dans le contrat Recruitment. Le candidat conserve son lifecycle Recruitment séparé.

## Distinction des coûts

Deux notions restent volontairement distinctes :

1. `candidate_direct_ai_cost_eur`
   - coût IA directement attribué au candidat par `AICostMetrics.by_agent` / `AgentMetrics.total_cost_eur` ;
2. `marginal_total_ai_cost_eur`
   - delta du coût IA total entre `WITH_CANDIDATE` et `BASELINE`, repris de `AblationComparison.additional_ai_cost_eur`.

Ces valeurs peuvent être différentes si la présence du candidat modifie aussi le comportement/coût des incumbents.

Le rapport conserve également :

- part du coût direct candidat dans le coût total du twin candidat ;
- budget déclaré du candidat ;
- ratio d'utilisation du budget ;
- indicateur `candidate_direct_cost_within_budget`.

Un dépassement est enregistré comme **évidence** ; ce step ne déclenche aucune action automatique.

## Nature de la donnée coût

Les coûts sont explicitement qualifiés :

`ESTIMATED_AI_USAGE_EUR_IN_SIMULATED_HISTORICAL_REPLAY_PAPER`

Ils ne doivent donc pas être présentés comme des dépenses LIVE réalisées.

## Contrôles de cohérence

Le builder :

- recalcule le bridge avant de l'accepter ;
- refuse un bridge stale/altéré ;
- exige exactement un `AgentMetrics` candidat dans `WITH_CANDIDATE` ;
- refuse toute présence du candidat dans les métriques/coûts de `BASELINE` ;
- vérifie `AgentMetrics.total_cost_eur == ai_costs.by_agent[candidate]` ;
- vérifie les coûts totaux Evaluation ↔ `BacktestPeriodReport` ;
- vérifie le delta total IA ↔ `AblationComparison.additional_ai_cost_eur` ;
- exige la même version de rapport Evaluation sur les deux twins.

## Gouvernance

Le rapport reste :

- `auto_apply = False` ;
- `registry_mutation = False` ;
- `promotion_action = False` ;
- `live_authority = False`.

Il ne crée ni ne modifie `AgentRegistryEntry`, ne touche pas au Risk Engine et ne donne aucune autorité LIVE.

## Installation

Extraire l'archive à la racine du dépôt.

## Tests

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
```

Puis :

```powershell
git status --short
```

Ne pas commit/push avant validation locale. Ne pas utiliser `git add -A`.
