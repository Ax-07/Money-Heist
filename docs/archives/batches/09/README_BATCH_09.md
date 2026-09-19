# Money Heist — Batch 09 — Pipeline PAPER complet

## Base requise

Le lot est préparé pour être extrait sur le dépôt au commit :

```text
00f5721 feat(orchestration): complete Batch 08 Orchestration
```

Le dépôt doit être propre avant extraction.

## Intégration

Depuis `E:\0 money heist` :

1. extraire le ZIP directement à la racine du projet ;
2. vérifier les changements avec `git status --short` ;
3. lancer :

```powershell
uv sync
uv run pytest -q
```

Aucune migration, nouvelle dépendance ou variable d’environnement n’est nécessaire.

Les 156 tests existants doivent rester verts. Le lot ajoute 34 cas de test ; le total attendu est donc **190 tests**.

## Runtime ajouté

```text
CandidateOpportunity
    ↓
OrchestrationPipeline Batch 08
    ↓
NO_ANALYSIS / NO_TRADE / FAILED ──> terminal, aucun Risk Engine/broker
    ↓ TradeProposal
Adaptateur déterministe
    ↓ TradeProposalRiskInput
Providers de contexte de risque
    ↓
Risk Engine
    ├─ REJECTED ──> terminal, aucun ordre
    ├─ APPROVED
    └─ RESIZED
          ↓
    quantité autorisée exacte
          ↓
    PaperOrderIntent (PAPER uniquement)
          ↓
    PaperBroker existant
          ↓
    BrokerOrder -> Fill -> Position
```

## Fourniture des données de risque

Le pipeline exige explicitement :

- `PortfolioRiskStateProvider` ;
- `RiskProfileProvider` ;
- `MarketConstraintsProvider` ;
- `KillSwitchStateProvider`.

Des implémentations en mémoire sont fournies pour PAPER/tests. Elles n’inventent aucune valeur absente : une clé manquante renvoie `None`, puis le pipeline s’arrête proprement avant toute nouvelle position.

## Mark d’exécution PAPER

Le `PaperBroker` est alimenté avec `FeatureSnapshot.close` provenant exactement du snapshot déjà transmis au Batch 08.

Le prix d’entrée proposé par le Professor n’est pas utilisé comme prix de fill. Le `PaperBroker` conserve donc son modèle existant de slippage/frais et calcule lui-même le fill.

## Idempotence

Le journal doit réussir son preflight avant le chemin d’exécution. Une fois le Risk Engine autorisé :

- `opportunity_id` et `proposal_id` sont réservés ;
- le `client_order_id` est déterministe à partir de l’opportunité ;
- un rerun ne peut pas produire un second fill.

`InMemoryPaperPipelineJournal` correspond au niveau de persistance actuel du `PaperBroker` V1. Une persistance durable pourra remplacer ce port plus tard sans donner de nouvelle permission aux agents.

## Audit minimal Batch 09

Les événements enregistrent au minimum :

- opportunité et snapshot ;
- statut orchestration et IDs des requêtes agents ;
- proposition et IDs Professor/spécialistes/Palermo ;
- décision et reason codes Risk Engine ;
- intention PAPER et quantité autorisée ;
- ordre ;
- fill ;
- position résultante.

Les métriques PnL agrégées, attribution agents, coût IA consolidé, self-funding ratio et rapports Lisbon restent volontairement au Batch 10.

## Limites volontaires

Ce lot n’ajoute pas :

- LIVE ;
- SHADOW multi-systèmes ;
- exchange adapter ;
- Rio ;
- Denver ;
- Dashboard ;
- nouvelles métriques Evaluation ;
- nouvelles dépendances.
