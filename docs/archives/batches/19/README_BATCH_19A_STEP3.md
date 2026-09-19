# Batch 19a — Step 3 — Population, Budget & Recruitment Frequency Gates

## Objectif

Ajouter les garde-fous déterministes de capacité du Recruitment Engine sans modifier le Risk Engine,
le broker, le LIVE, `AgentRegistry` ou la réputation Batch 18.

Ce step ne décide pas si un candidat est performant. Il vérifie uniquement si une action de
recrutement reste dans des limites opérateur explicitement fournies.

## Contrats ajoutés

- `RecruitmentCapacityPolicy`
- `RecruitmentCapacitySnapshot`
- `RecruitmentGateStatus`
- `RecruitmentGateDecision`
- `RecruitmentComputeRequest`
- `RecruitmentComputeDecision`
- `evaluate_shadow_admission()`
- `evaluate_candidate_compute()`

## Invariants

Les seuils de capacité sont obligatoirement injectés par l'appelant :

- `max_active_specialists`
- `max_shadow_candidates`
- `max_recruitments_per_period`
- `max_compute_per_candidate_eur`

Aucune valeur de production n'est inventée par le code.

`evaluate_shadow_admission()` vérifie :

- état recruitment `CANDIDATE` ;
- capacité des spécialistes actifs ;
- capacité des candidats SHADOW ;
- fréquence de recrutement sur une période explicite ;
- compatibilité du budget candidat avec la politique opérateur.

Un résultat `ALLOW` ne change aucun état. La transition `ENTER_SHADOW` reste un Step 2 séparé et
nécessite encore `operator_authorized=True`.

`evaluate_candidate_compute()` applique la limite la plus stricte entre :

- `RecruitmentCandidateSpec.budget_limit_eur` ;
- `RecruitmentCapacityPolicy.max_compute_per_candidate_eur`.

Le résultat ne déclenche aucun appel IA et contient explicitement `execute_compute=False`.

## Sécurité

Le Step 3 :

- n'importe pas le Risk Engine ;
- n'importe pas de broker LIVE ;
- n'importe pas `AgentRegistryEntry` ;
- ne mute pas `AgentRegistry` ;
- n'applique aucune transition ;
- ne possède aucune autorité LIVE ;
- ne réimplémente pas réputation/ablation Batch 18.

Les décisions possèdent un fingerprint SHA-256 déterministe pour l'audit.

## Installation

Extraire le ZIP à la racine du repository après les Steps 1 et 2.

Puis exécuter :

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Ne pas commit/push avant revue des résultats.
