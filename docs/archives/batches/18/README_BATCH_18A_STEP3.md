# Money Heist — Batch 18a Step 3

## Bridge réputation / ablation vers recommandation auditable

Ce Step 3 relie les contrats déjà installés :

```text
AgentMetrics + AblationComparison(s)
        ↓
AblationAggregate (Step 1)
        ↓
AgentReputationProfile (Step 1)
        ↓
AgentStateEvidence (Step 2)
        ↓
DeterministicAgentStateAdvisor (Step 2)
        ↓
AgentReputationAdvisoryReport (Step 3)
```

Le rapport conserve la provenance des expériences et un fingerprint SHA-256 déterministe.
Il ne modifie jamais `AgentRegistry` et `auto_apply` reste toujours `False`.

## Règles conservatrices

- les seuils `ReputationPolicy` et `ReputationPolicyThresholds` sont fournis explicitement ;
- une preuve d'ablation utilisée pour une transition d'état doit être OOS-only ;
- DESIGN/VALIDATION ne sont jamais requalifiés en OOS ;
- une métrique indisponible reste indisponible ;
- le coût agent ne peut pas dépasser le coût IA total du même scope ;
- aucun score global opaque n'est créé ;
- aucune recommandation ne touche Risk, Broker, PAPER ou LIVE.

## Installation

Extraire le ZIP à la racine du dépôt après les Steps 1 et 2.

## Tests

```powershell
uv run pytest -q tests/evaluation/test_reputation_advisory.py
uv run pytest -q
```

## Note d'intégration

Ce lot ne remplace pas `app/evaluation/__init__.py`. Les exports publics pourront être consolidés
lors de la fermeture de Batch 18a afin d'éviter d'écraser les modifications locales déjà validées.
