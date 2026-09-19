# Money Heist — Batch 07a Core Agents — v2

## Installation

Extraire le contenu de `money-heist_batch_07a_core-agents_v2.zip` directement à la racine du dépôt Money Heist en autorisant l'écrasement des fichiers du premier ZIP 07a.

Puis :

```powershell
uv sync
uv run pytest -q
```

## Périmètre

- The Professor
- Palermo
- Lisbon
- registre d'agents Core
- versionnage des prompts
- tests des frontières de sécurité agentiques

Aucune nouvelle dépendance. Aucun secret. Aucun accès broker/exchange. Aucune modification du Risk Engine ni du budget IA.

## Correctif v2

Le mock de test respecte désormais intégralement les champs obligatoires de `AIUsageRecord` et `AIGatewayResult` introduits par le Batch 06.
