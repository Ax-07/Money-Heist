# Money Heist — État actuel post-Batch 15

**Statut :** Référence d’alignement active  
**Date :** 2026-09-07  
**Baseline code :** `40c4144e0880300a7910cbdb14f27d6764b34b84` — `feat(live): complete Batch 15 LIVE activation guardrails`

---

## 1. Rôle de ce document

Ce document corrige le décalage entre la documentation initiale créée avant le développement et l’état réel du dépôt après les Batchs 01 à 15.

En cas de contradiction entre une formulation historique des documents `01_...` à `08_...` et l’état décrit ici, **ce document, `09_ROADMAP_DEVELOPPEMENT.md`, `10_DECISIONS_ET_CHANGELOG.md` et le code intégré sur GitHub `main` prévalent pour décrire l’état actuel**.

Les documents historiques restent utiles pour les principes, invariants et intentions architecturales qui n’ont pas été explicitement superseded.

---

## 2. État implémenté

Les Batchs suivants sont livrés :

```text
01 — Fondations
02 — Market Data Core
03 — Feature Engine et Scanner
04 — Paper Broker
05 — Risk Engine
06 — AI Gateway
07a — Core Agents
07b — Spécialistes V1
08 — Orchestration complète
09 — Pipeline PAPER complet
10 — Evaluation
11 — Systèmes SHADOW
12 — Dashboard V1
13 — Exchange Adapter / Market Data réel Kraken
14 — LIVE Broker sécurisé Kraken Spot / EUR
15 — Activation LIVE / garde-fous fail-closed
```

Le Batch 15 ne signifie pas qu’un premier ordre réel a été envoyé ni qu’il doit l’être immédiatement.

---

## 3. État LIVE

Le premier chemin LIVE cible :
- Kraken Spot / EUR ;
- `balanced_v1` ;
- `BTC/EUR`, `ETH/EUR`, `SOL/EUR` ;
- sans marge, dérivés ou levier pour le premier LIVE ;
- sans entrée SHORT LIVE.

Le mécanisme Batch 15 est fail-closed :

```text
LIVE_DISABLED
→ LIVE_PREFLIGHT
→ LIVE_ARMED
```

L’armement est opérateur, explicite, éphémère et perdu au redémarrage.

La présence de credentials Kraken ne suffit jamais à armer le LIVE.

Restent notamment bloquants avant tout premier ordre réel :
- profil Balanced numérique complet et validé ;
- timeframes de production validés ;
- seuils de fraîcheur Market Data validés ;
- validation historique end-to-end définie ci-dessous.

---

## 4. Écart identifié après Batch 15

Le dépôt possède déjà :
- import OHLCV historique ;
- Feature Engine replay-safe ;
- `replay_scanner()` sans look-ahead ;
- Paper Broker avec capital virtuel, frais, slippage, stops et replay de prix ;
- pipeline `Opportunity → AI → Risk → Paper Broker` ;
- Evaluation ;
- SHADOW multi-systèmes.

Mais il ne possède pas encore un moteur historique end-to-end qui boucle chronologiquement :

```text
candles
→ Feature Engine
→ Scanner
→ Opportunity
→ Agents
→ Risk Engine
→ Paper Broker
→ cycle de vie de position
→ equity / PortfolioRiskState évolutif
→ Evaluation
```

L’out-of-sample et le walk-forward sont spécifiés, mais pas encore implémentés end-to-end.

---

## 5. Nouvelle gate avant premier LIVE réel

La séquence obligatoire devient :

```text
Replay historique
→ Backtest end-to-end
→ Validation hors échantillon
→ Walk-forward
→ PAPER / SHADOW
→ Preflight LIVE
→ décision opérateur
→ Petit capital réel
```

Le LIVE doit rester **non armé** tant que cette gate n’est pas satisfaite.

---

## 6. Batch 16 — Backtesting & Historical Replay

Le nouveau Batch 16 doit notamment fournir :
- `HistoricalReplayRunner` ;
- `ReplayClock` ;
- datasets historiques identifiables/versionnés ;
- réutilisation du Feature Engine et Scanner de production ;
- orchestration agents sur données disponibles au timestamp simulé uniquement ;
- Risk Engine identique au chemin PAPER ;
- capital, equity, exposition et `PortfolioRiskState` évolutifs ;
- cycle de vie complet des positions, stops et targets ;
- modèle de fills historique avec frais/slippage ;
- politique déterministe et conservatrice pour ambiguïtés intrabar ;
- equity curve ;
- résultats Evaluation ;
- modes IA explicitement séparés : `MOCK`, `CACHED`, `LIVE_EVAL` ;
- out-of-sample ;
- walk-forward V1 ;
- exports reproductibles ;
- tests anti-look-ahead.

Un run doit identifier son dataset, sa période, ses versions Feature/Scanner/Risk/Prompts/Models, son mode IA et ses hypothèses d’exécution.

---

## 7. Roadmap réalignée

```text
Batch 16 — Backtesting & Historical Replay
Batch 17 — Rio / Denver avancés
Batch 18 — Réputation et ablation
Batch 19 — Recruitment Engine
Batch 20 — Task Force Agents
Batch 21 — Master Portfolio Layer
```

Denver avancé vient volontairement après Batch 16 afin de consommer des statistiques historiques réellement produites par le système plutôt que des probabilités inventées.

---

## 8. Source de vérité documentaire

À partir de cette révision :

1. GitHub `Ax-07/Money-Heist`, branche `main`, représente l’état intégré du projet.
2. `00_ETAT_ACTUEL_POST_BATCH_15.md` décrit l’alignement courant.
3. `09_ROADMAP_DEVELOPPEMENT.md` porte la roadmap active.
4. `10_DECISIONS_ET_CHANGELOG.md` porte les ADR et décisions ouvertes.
5. Les documents `01_...` à `08_...` restent des références de domaine ; toute formulation historique devenue contradictoire avec les points 1 à 4 est considérée comme superseded jusqu’à sa prochaine consolidation éditoriale.
6. Les copies chargées comme sources du projet ChatGPT doivent être resynchronisées avec GitHub après une révision documentaire approuvée.

---

## 9. Prochaine étape

Après fusion de cet alignement documentaire :

**Démarrer Batch 16 — Backtesting & Historical Replay, avec LIVE non armé.**
