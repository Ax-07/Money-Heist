# CHANGELOG — Batch 09 — Pipeline PAPER complet

## Base d’intégration

- Dépôt : `Ax-07/Money-Heist`
- Branche : `main`
- Commit de référence : `00f57219bff261eb673defde1b9474c682e9e9ef`
- Batch précédent : `08 — Orchestration complète`

## Ajouté

### `app/services/paper_pipeline/`

Nouveau service déterministe reliant les composants déjà présents :

```text
CandidateOpportunity
-> OrchestrationPipeline Batch 08
-> TradeProposal
-> TradeProposalRiskInput
-> Risk Engine
-> APPROVED / RESIZED / REJECTED
-> Paper Broker
-> BrokerOrder / Fill / Position
```

Le module contient :

- `models.py`
  - statuts et erreurs du pipeline PAPER ;
  - wrapper traçable de `RiskDecision` ;
  - `PaperOrderIntent` exclusivement PAPER ;
  - événements d’audit minimaux ;
  - résultat end-to-end avec ordre, fill et positions avant/après.

- `ports.py`
  - port d’orchestration Batch 08 ;
  - providers explicites pour `PortfolioRiskState`, `RiskProfile`, `MarketConstraints` et `KillSwitchState` ;
  - contrat de journal/audit/idempotence.

- `providers.py`
  - providers déterministes en mémoire sans valeur implicite ;
  - une donnée absente reste absente et fait échouer le pipeline avant le Risk Engine ou le broker selon le cas.

- `journal.py`
  - journal en mémoire cohérent avec le `PaperBroker` V1 lui-même en mémoire ;
  - preflight d’audit ;
  - réservation atomique de `opportunity_id` et `proposal_id` avant exécution.

- `adapters.py`
  - adaptation stricte `TradeProposal -> TradeProposalRiskInput` ;
  - aucune quantité n’est reprise de l’IA ;
  - création d’intention uniquement à partir d’une décision `APPROVED`/`RESIZED` ;
  - quantité exactement égale à `RiskDecision.approved_quantity` ;
  - `client_order_id` déterministe au niveau de l’opportunité.

- `pipeline.py`
  - `NO_ANALYSIS` et `NO_TRADE` terminaux sans Risk Engine ni broker ;
  - arrêt sûr sur orchestration `FAILED` ;
  - validation des liens opportunity/snapshot/system/symbol/timeframe ;
  - chargement obligatoire des quatre contextes de risque ;
  - Risk Engine autoritatif ;
  - `REJECTED` ne peut pas atteindre le broker ;
  - `APPROVED` et `RESIZED` créent uniquement un ordre PAPER `MARKET` ;
  - mark PAPER issu du `FeatureSnapshot.close` exact utilisé par l’orchestration ;
  - frais, slippage, fill et position produits par le `PaperBroker` existant ;
  - traçabilité `opportunity -> analyses -> proposal -> risk -> order -> fill -> position`.

## Idempotence

Deux niveaux complémentaires :

1. le journal réserve simultanément `opportunity_id` et `proposal_id` avant l’ordre ;
2. le `client_order_id` Paper Broker est dérivé de l’`opportunity_id`, ce qui conserve le garde-fou d’idempotence déjà fourni par le Batch 04.

Une seconde exécution retourne `DUPLICATE_BLOCKED` et ne crée aucun fill supplémentaire.

## Sécurité

- PAPER uniquement ;
- aucun `LiveBroker` ;
- aucun exchange adapter ;
- aucun secret ;
- aucune clé API ;
- aucun changement de permission ;
- les agents et l’orchestration Batch 08 ne reçoivent toujours aucun accès au Risk Engine ou au Paper Broker ;
- aucun fallback transformant `NO_TRADE`, une erreur IA ou une donnée manquante en trade ;
- aucun profil/état portefeuille/contrainte marché par défaut n’est inventé.

## Evaluation

Batch 09 n’implémente aucune métrique complète du Batch 10.

Seuls les événements structurés minimaux nécessaires au futur branchement de l’évaluation sont ajoutés.

## Tests ajoutés

34 cas de test Batch 09 au total, couvrant notamment :

- end-to-end réel Batch 08 -> Risk -> Paper Broker ;
- LONG nominal ;
- SHORT nominal avec le contrat Paper actuel ;
- `NO_ANALYSIS` ;
- `NO_TRADE` ;
- erreur IA structurée en amont ;
- budget IA insuffisant en amont ;
- `APPROVED` ;
- `RESIZED` et quantité strictement autorisée ;
- `REJECTED` ;
- expiration ;
- stop invalide ;
- daily loss ;
- drawdown ;
- kill switch ;
- max positions ;
- risque portefeuille/exposition/leverage ;
- quantité minimale ;
- notional minimal ;
- portefeuille manquant ;
- profil de risque manquant ;
- contraintes marché manquantes ;
- kill-switch state manquant ;
- adaptation `TradeProposal -> TradeProposalRiskInput` ;
- chaîne complète des identifiants ;
- idempotence ;
- erreur broker intermédiaire ;
- indisponibilité du journal ;
- frontières d’import agents / Risk / Broker ;
- impossibilité de construire un `PaperOrderIntent` LIVE.

## Validation effectuée sur le lot

- compilation Python de tous les nouveaux fichiers : OK ;
- 31 tests du cœur Batch 09 exécutés contre un miroir local des contrats Batch 04/05/08 : `31 passed` ;
- les 3 tests d’intégration utilisant le vrai AI Gateway Batch 08 sont inclus dans le ZIP et doivent être confirmés avec la suite complète du dépôt.

Avec les 156 tests existants, le total attendu après intégration est **190 tests**.

## Dépendances

Aucune nouvelle dépendance.
