# Money Heist — Batch 08 — Orchestration complète

## Base requise

Le lot est préparé pour être extrait sur le dépôt après :

`e8ad3ab feat(agents): complete Batch 07b Specialists V1`

## Intégration

Depuis `E:\0 money heist` :

1. vérifier que le dépôt est propre ;
2. extraire le contenu du ZIP directement à la racine ;
3. lancer `uv sync` ;
4. lancer `uv run pytest -q`.

Aucune migration, variable d’environnement ou nouvelle dépendance n’est nécessaire.

## Périmètre runtime

Le Batch 08 s’arrête volontairement à `TradeProposal`.

```text
CandidateOpportunity
-> Compute Gate
-> The Professor (plan)
-> Berlin / Tokyo / Nairobi (tour 1 indépendant)
-> Palermo
-> The Professor (décision finale stricte)
-> NO_TRADE ou TradeProposal
```

Le Risk Engine et le Paper Broker seront reliés au pipeline dans le Batch 09.

## Fail-safe

Une sortie IA invalide, une preuve non fondée, un contexte incohérent ou un budget insuffisant produit `NO_ANALYSIS` ou `FAILED` sans `TradeProposal`. Aucun fallback libre vers un trade n’est effectué.
