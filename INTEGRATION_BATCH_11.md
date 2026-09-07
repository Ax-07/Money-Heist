# Intégration — Batch 11 — Systèmes SHADOW

## Pré-requis

Le dépôt local doit déjà contenir les Batchs 01 à 10 et votre suite actuelle de 215 tests doit être verte avant intégration.

Ce lot est additif pour le code applicatif : il crée `app/services/shadow/` et `tests/shadow/`. Il remplace uniquement le fichier de livraison racine `CHANGELOG_BATCH.md`, comme les batchs précédents.

## Installation

Depuis PowerShell :

```powershell
Set-Location 'E:\0 money heist'
git status --short
```

Le `git status` doit idéalement être propre. Extraire ensuite le ZIP directement à la racine du dépôt en conservant l'arborescence.

Puis lancer :

```powershell
uv sync
uv run pytest -q
```

Avec exactement 215 tests avant ce batch, le total attendu après intégration est **264 tests** : 215 existants + 49 tests Batch 11.

## Raccordement à Evaluation Batch 10

Le runner SHADOW accepte une implémentation de `Batch10EvaluationPort`. Le lot fournit `CallableBatch10EvaluationAdapter`, qui évite de faire dépendre le pipeline PAPER de l'implémentation concrète d'Evaluation.

Le contrat transmis à Batch 10 contient, pour un seul système :

- `system_id` ;
- `root_opportunity_id` ;
- `derived_opportunity_id` ;
- l'historique `PaperPipelineResult` du système ;
- les éventuels `AIUsageRecord` explicitement rattachés à ce système.

Le projecteur de métriques doit retourner un `ShadowMetricSnapshot`. `MappingMetricProjector` est fourni lorsque l'export Batch 10 est un mapping avec les clés standards `realized_pnl`, `trading_net`, `economic_net`, `ai_cost` et `self_funding_ratio`.

Aucune métrique absente n'est reconstruite ou remplacée par zéro. Sans evaluator injecté, Evaluation reste `NOT_REQUESTED` et les comparaisons concernées restent `UNAVAILABLE` ; le PAPER continue de fonctionner.

## Construction d'un runtime SHADOW

`build_shadow_runtime(...)` demande explicitement :

- une identité SHADOW ;
- une orchestration propre au système ;
- une `PaperBrokerConfig` dont le `system_id` correspond à l'identité ;
- un `PortfolioRiskState` ;
- des `MarketConstraints` ou un provider immuable ;
- éventuellement un `RiskProfile` explicite.

Si `risk_profile=None`, le factory utilise `unresolved_profile(...)`. Le Risk Engine existant rejette alors la nouvelle position avec `PROFILE_INCOMPLETE`. Aucun seuil chiffré n'est inventé.

## Règles d'isolation appliquées

Le `ShadowFleetRunner` refuse avant exécution le partage implicite d'un objet stateful entre systèmes. Les données de marché immuables peuvent être partagées. Le même `RiskEngine` déterministe peut également être réutilisé, car son état de décision est fourni par ses entrées et ses règles ne sont pas modifiées par ce batch.

## Vérification avant commit

```powershell
uv run pytest -q
git diff --check
git status --short
```

Ne committer le Batch 11 qu'après validation de la suite locale complète.
