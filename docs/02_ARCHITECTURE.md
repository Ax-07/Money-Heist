# Money Heist — Architecture Technique

**Document :** Architecture technique  
**Version :** 0.1  
**Statut :** Spécification initiale  
**Référence :** `01_PROJECT_MASTER.md`

---

## 1. Objectif

Ce document décrit l’architecture logique de Money Heist : composants, responsabilités, frontières de sécurité, flux de données, modes d’exécution et dépendances.

Il ne fige pas encore les décisions explicitement laissées ouvertes dans le document maître, notamment :
- exchange initial ;
- spot ou dérivés ;
- timeframes exacts ;
- limites numériques du profil Balanced ;
- base de données finale ;
- environnement de déploiement.

L’architecture doit permettre de prendre ces décisions sans réécriture majeure.

---

## 2. Principes d’architecture

Money Heist suit six règles structurantes :

1. **Séparation analyse / autorisation / exécution.**
2. **Aucune décision IA ne déclenche directement un ordre réel.**
3. **Les fonctions critiques sont déterministes et testables.**
4. **PAPER, SHADOW et LIVE partagent autant que possible le même pipeline.**
5. **Chaque décision est traçable et reproductible.**
6. **Les composants IA sont remplaçables sans modifier le cœur du trading.**

---

## 3. Vue d’ensemble

```text
                       ┌────────────────────────┐
                       │      MARKET DATA       │
                       │ OHLCV / trades / etc.  │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │ NORMALISATION / CACHE  │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │ SCANNER DÉTERMINISTE   │
                       └───────────┬────────────┘
                                   │ CandidateOpportunity
                                   ▼
                       ┌────────────────────────┐
                       │ AI COMPUTE GATE        │
                       │ budget + priorité      │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │     THE PROFESSOR      │
                       │ orchestration          │
                       └───────────┬────────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
             Berlin              Tokyo             Nairobi
                │                  │                  │
                └──────────────┬───┴───────┬─────────┘
                               ▼           ▼
                              Rio        Denver
                               └──────┬────┘
                                      ▼
                                  Palermo
                                      │
                                      ▼
                              The Professor
                                      │ TradeProposal
                                      ▼
                       ┌────────────────────────┐
                       │ RISK ENGINE            │
                       │ déterministe           │
                       └───────────┬────────────┘
                                   │ AuthorizedTrade
                                   ▼
                       ┌────────────────────────┐
                       │ EXECUTION ROUTER       │
                       └───────┬────────┬───────┘
                               │        │
                           PAPER     LIVE
                               │        │
                               └───┬────┘
                                   ▼
                       ┌────────────────────────┐
                       │ JOURNAL / EVALUATION   │
                       └───────────┬────────────┘
                                   ▼
                               Lisbon
```

---

## 4. Couches principales

### 4.1 Configuration

Responsabilités :
- charger la configuration non sensible ;
- charger les références vers les secrets sans les exposer aux agents ;
- définir le mode `PAPER`, `SHADOW` ou `LIVE` ;
- définir l’univers de marché ;
- définir les profils de risque ;
- définir les budgets IA ;
- définir le routage de modèles.

Contraintes :
- configuration typée ;
- validation au démarrage ;
- échec explicite si une valeur critique manque ;
- aucune valeur secrète dans les logs.

---

### 4.2 Market Data

Responsabilités :
- collecter les données brutes ;
- valider leur fraîcheur ;
- normaliser les formats ;
- détecter les trous de données ;
- produire des snapshots cohérents ;
- exposer des données stables aux calculs.

Le reste du système ne doit pas dépendre directement du format spécifique d’un exchange.

Interface conceptuelle :

```python
class MarketDataProvider:
    async def get_snapshot(self, symbol: str) -> MarketSnapshot: ...
    async def get_candles(self, symbol: str, timeframe: str, limit: int): ...
```

---

### 4.3 Feature Engine

Responsabilités :
- calcul des indicateurs ;
- structure de marché ;
- métriques de volatilité ;
- métriques de volume ;
- variables quantitatives ;
- construction d’un snapshot compact pour les agents.

L’objectif est de **ne pas envoyer des séries brutes massives aux LLM** lorsque des features déterministes suffisent.

---

### 4.4 Scanner

Le scanner fonctionne sans modèle IA dans sa forme de base.

Il produit une `CandidateOpportunity` lorsqu’un événement mérite une inspection.

Exemples de familles de triggers :
- breakout ;
- changement de régime ;
- expansion inhabituelle de volatilité ;
- volume anormal ;
- variation d’open interest ;
- divergence ;
- proximité d’une zone importante.

Le scanner ne décide jamais `LONG` ou `SHORT` à lui seul.

---

### 4.5 AI Compute Gate

Ce composant protège le budget IA.

Entrées :
- opportunité ;
- priorité ;
- budget restant ;
- coût estimé ;
- niveau d’analyse requis.

Sorties :
- `SKIP_AI` ;
- `LEVEL_1_SENTINEL` ;
- `LEVEL_2_MINI_CREW` ;
- `LEVEL_3_FULL_CREW`.

Les limites dures sont appliquées par code.

---

### 4.6 Orchestrateur Money Heist

The Professor orchestre les spécialistes via une interface commune.

Responsabilités :
- décider quels spécialistes appeler ;
- garantir le minimum de contradiction requis ;
- préserver l’indépendance du premier tour ;
- compiler les analyses ;
- décider si un second tour vaut son coût ;
- produire une proposition finale structurée.

L’orchestrateur ne reçoit pas les clés exchange et n’appelle jamais directement le connecteur d’exécution LIVE.

---

### 4.7 Risk Engine

Composant déterministe.

Entrée :

```text
TradeProposal
+
PortfolioState
+
RiskProfile
+
MarketConstraints
```

Sortie :

```text
APPROVED
REJECTED
RESIZED
```

Toute modification d’une proposition doit être explicitement journalisée.

---

### 4.8 Execution Router

Route une décision autorisée vers :
- `PaperBroker` ;
- `LiveBroker`.

Le mode est défini par la configuration du système et ne peut pas être changé par un agent.

---

### 4.9 Storage / Journal

Stockage de :
- market snapshots utilisés ;
- opportunités ;
- exécutions d’agents ;
- coûts IA ;
- propositions ;
- décisions Risk Engine ;
- ordres ;
- fills ;
- positions ;
- résultats ;
- événements de sécurité ;
- changements de configuration.

Chaque objet majeur possède un identifiant stable.

---

### 4.10 Evaluation

Responsabilités :
- calcul des performances ;
- calibration des agents ;
- attribution marginale ;
- comparaison des crews ;
- évaluation des profils SHADOW ;
- préparation des données pour Lisbon.

Aucune métrique d’évaluation ne doit modifier immédiatement les règles LIVE sans processus contrôlé.

---

## 5. Modèle événementiel

Le prototype peut commencer comme une application monolithique modulaire, tout en utilisant un modèle d’événements interne.

Événements conceptuels :

```text
MarketSnapshotCreated
CandidateOpportunityCreated
AIAnalysisRequested
AgentAnalysisCompleted
TradeProposalCreated
RiskDecisionCreated
OrderSubmitted
OrderFilled
PositionOpened
PositionClosed
AICostRecorded
SafetyLimitTriggered
```

Objectif :
- découpler les composants ;
- faciliter les tests ;
- reconstruire une décision ;
- permettre une migration future vers une architecture distribuée si nécessaire.

---

## 6. Pipeline runtime

### 6.1 Surveillance

```text
1. Réception des données
2. Validation
3. Normalisation
4. Calcul des features
5. Scanner
6. Création éventuelle d’une opportunité
```

### 6.2 Analyse IA

```text
1. Compute Gate
2. Professor : plan d’analyse
3. Spécialistes en parallèle
4. Agrégation
5. Palermo
6. Professor : proposition finale
```

### 6.3 Autorisation et exécution

```text
1. Validation du schéma
2. Risk Engine
3. Rejet ou autorisation
4. Execution Router
5. Paper/Live Broker
6. Réconciliation
7. Journalisation
```

### 6.4 Evaluation

```text
1. Mise à jour position
2. Calcul du résultat
3. Attribution
4. Calcul des coûts
5. Mise à jour des métriques agent
6. Rapport Lisbon
```

---

## 7. PAPER, SHADOW et LIVE

### PAPER

Simulation complète avec capital virtuel.

Aucun appel d’ordre réel.

### SHADOW

Le système peut fonctionner en parallèle d’un système LIVE.

Il :
- observe les mêmes marchés ;
- prend ses propres décisions ;
- simule ses trades ;
- n’influence pas le système LIVE.

### LIVE

Les décisions autorisées peuvent être envoyées à l’exchange.

Conditions minimales avant activation :
- Risk Engine validé ;
- kill switch fonctionnel ;
- tests de réconciliation ;
- API sans droit de retrait ;
- plafond de risque configuré ;
- logs persistants ;
- comportement fail-safe vérifié.

---

## 8. Isolation des systèmes

Chaque profil ou crew doit avoir :
- son `system_id` ;
- son portefeuille logique ;
- sa configuration ;
- son budget IA ;
- ses métriques ;
- son état LIVE/SHADOW.

Les données de marché peuvent être partagées.

Les décisions, budgets et expositions ne doivent pas être implicitement partagés.

---

## 9. Frontières de panne

### Données invalides
Action : bloquer toute nouvelle position utilisant ces données.

### API IA indisponible
Action : pas de nouvelle proposition IA ; gestion déterministe des positions déjà ouvertes.

### Sortie IA invalide
Action : rejet de l’analyse ; possibilité d’un retry borné.

### Base de données indisponible
Action : par défaut, bloquer les nouvelles positions si l’audit ne peut pas être garanti.

### Exchange indisponible
Action : ne pas ouvrir de nouvelles positions ; tenter uniquement les actions de sécurité autorisées selon le contexte.

### Budget IA épuisé
Action : aucune dépense supplémentaire ; bascule possible vers analyse déterministe ou arrêt des nouvelles analyses IA.

---

## 10. Concurrence et idempotence

Le système doit éviter :
- double exécution ;
- double traitement d’une opportunité ;
- répétition d’un ordre après timeout ;
- deux décisions concurrentes sur la même position sans arbitrage.

Concepts requis :
- `event_id` ;
- `opportunity_id` ;
- `proposal_id` ;
- `client_order_id` ;
- verrou logique par système/symbole si nécessaire ;
- opérations idempotentes.

---

## 11. Déploiement V1

La V1 doit privilégier la simplicité :

```text
Une application backend
+
Une base de données
+
Un scheduler / loop de marché
+
Un dashboard web
```

Une architecture microservices n’est pas nécessaire au départ.

Le code doit cependant conserver des frontières de modules suffisamment nettes pour permettre une extraction future.

---

## 12. Observabilité

Minimum :
- logs structurés ;
- niveaux INFO/WARNING/ERROR/CRITICAL ;
- identifiants de corrélation ;
- métriques de latence ;
- coût IA ;
- erreurs API ;
- état des connexions ;
- alertes sécurité ;
- nombre d’opportunités ;
- nombre de propositions ;
- nombre de rejets.

---

## 13. Dépendances autorisées entre couches

Règle générale :

```text
api
 ↓
services/orchestration
 ↓
domain
 ↓
ports/interfaces

infrastructure
 ↑ implémente les ports
```

Éviter que :
- les agents importent directement l’exchange ;
- le Risk Engine dépende du SDK IA ;
- la logique métier dépende du framework FastAPI ;
- la base de données dicte les objets métier.

---

## 14. Décisions à prendre avant Batch 01

Batch 01 ne nécessite pas encore le choix de l’exchange.

Il faut toutefois figer :
- version Python cible ;
- gestionnaire de dépendances ;
- style de configuration ;
- type de base locale initiale ;
- framework de tests.

Ces décisions seront consignées dans `10_DECISIONS_ET_CHANGELOG.md`.

---

## 15. Critères d’acceptation de l’architecture

L’architecture est considérée correctement appliquée si :
- un agent ne peut pas exécuter directement un trade ;
- PAPER et LIVE utilisent les mêmes objets métier ;
- le Risk Engine est indépendant des LLM ;
- chaque appel IA est comptabilisé ;
- chaque proposition est liée au snapshot utilisé ;
- chaque ordre est lié à une décision autorisée ;
- une panne critique bloque les nouvelles positions ;
- un nouveau spécialiste peut être ajouté sans modifier le Risk Engine.
