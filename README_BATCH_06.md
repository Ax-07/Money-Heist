# Batch 06 — AI Gateway — Installation rapide

Ce lot est volontairement **additif** : il n'écrase ni le Risk Engine, ni le Paper Broker, ni les modèles des Batchs 01–05.

## Installation

Depuis la racine du projet après extraction :

```powershell
uv sync
uv run pytest -q
```

## Contrats principaux

- `AIGateway` : orchestration d'un appel structuré, budget + retries + validation.
- `AIClient` : interface fournisseur abstraite.
- `OpenAIResponsesClient` : adaptateur OpenAI Responses API.
- `MockAIClient` : fournisseur déterministe pour tests.
- `ModelRouter` : routes et fallbacks configurables.
- `AIBudgetLedger` : plafond dur de dépenses.
- `AIUsageRecord` : tokens, coût, latence, modèle, agent, tentative.

## Important

Le Batch 06 ne crée aucun agent. The Professor, Palermo, Lisbon et le registry arrivent au Batch 07a. Le gateway ne possède aucune capacité d'exécution exchange et n'importe aucun module de trading.
