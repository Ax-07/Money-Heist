# Money Heist — Roadmap de Développement

**Document :** Plan de développement par lots  
**Version :** 0.2  
**Statut :** Roadmap active — réalignée post-Batch 15

---

## 1. Objectif

Décomposer le développement en lots suffisamment petits pour :
- être testables ;
- être intégrables dans VS Code ;
- permettre des retours rapides ;
- éviter un gros ZIP opaque ;
- conserver une application fonctionnelle à chaque étape importante.

**Baseline au 2026-09-07 :** les Batchs 01 à 15 sont livrés sur `main`. Le Batch 15 a livré les garde-fous d’activation LIVE mais n’impose ni n’autorise automatiquement un premier ordre réel. L’audit post-Batch 15 a identifié le moteur historique end-to-end comme gate manquante ; il devient le Batch 16.

---

## 2. Convention de livraison

Chaque lot ZIP contient :
- arborescence de fichiers ;
- code ;
- tests ;
- `.env.example` si nécessaire ;
- `CHANGELOG_BATCH.md` ;
- instructions de lancement ;
- éventuelles migrations.

Exemple :

```text
money-heist_batch_01_foundation.zip
```

---

## 3. Batch 01 — Fondations

### Objectif
Créer un projet exécutable vide mais propre.

### Contenu
- structure Python ;
- gestion configuration ;
- logging ;
- modèles de base ;
- FastAPI ;
- health endpoint ;
- tests ;
- scripts de lancement ;
- base de données minimale.

### Critères
- installation propre ;
- `pytest` passe ;
- serveur démarre ;
- `/health` fonctionne ;
- configuration invalide échoue proprement.

---

## 4. Batch 02 — Market Data Core

### Objectif
Créer les interfaces de données et la normalisation.

### Contenu
- `MarketDataProvider` ;
- modèles candle/snapshot ;
- validation fraîcheur ;
- import historique simple ;
- tests.

Aucun exchange LIVE n’est requis si le choix n’est pas encore figé.

---

## 5. Batch 03 — Feature Engine et Scanner

### Contenu
- indicateurs initiaux ;
- feature snapshot ;
- règles scanner ;
- `CandidateOpportunity` ;
- scoring ;
- tests replay.

### Critère
Une série historique peut produire des opportunités reproductibles.

---

## 6. Batch 04 — Paper Broker

### Contenu
- compte virtuel ;
- ordres ;
- fills ;
- frais ;
- slippage ;
- positions ;
- PnL ;
- stops simples.

### Critère
Un scénario déterministe peut être rejoué avec le même résultat.

---

## 7. Batch 05 — Risk Engine

### Contenu
- profils de risque ;
- sizing ;
- limites ;
- reason codes ;
- kill switch ;
- tests de sécurité.

### Important
Les valeurs Balanced doivent être décidées avant finalisation de ce batch.

---

## 8. Batch 06 — AI Gateway

### Contenu
- client IA abstrait ;
- routage modèle configurable ;
- comptage tokens ;
- coût ;
- retry borné ;
- sortie structurée ;
- budget dur.

### Critère
Un mock IA permet tous les tests sans coût API.

---

## 9. Batch 07a — Core Agents

### Contenu
- The Professor ;
- Palermo ;
- Lisbon ;
- registry ;
- prompt versioning.

### Critère
Pipeline agentique fonctionnel sur données mockées.

---

## 10. Batch 07b — Spécialistes V1

### Contenu
- Berlin ;
- Tokyo ;
- Nairobi.

Rio et Denver peuvent être séparés si leurs données ne sont pas prêtes.

---

## 11. Batch 08 — Orchestration complète

```text
Scanner
→ Compute Gate
→ Professor
→ spécialistes
→ Palermo
→ Professor
→ TradeProposal
```

### Critères
- analyses indépendantes ;
- budget respecté ;
- sortie structurée ;
- audit complet.

---

## 12. Batch 09 — Pipeline PAPER complet

```text
Opportunity
→ AI
→ Risk
→ Paper Broker
→ Position
→ Evaluation
```

### Critère
Simulation end-to-end automatisée.

---

## 13. Batch 10 — Evaluation

### Contenu
- métriques trading ;
- coûts IA ;
- self-funding ratio ;
- métriques agents ;
- exports ;
- premiers rapports Lisbon.

---

## 14. Batch 11 — Systèmes SHADOW

### Contenu
- Conservative ;
- Balanced ;
- Aggressive ;
- isolation des portefeuilles ;
- comparaison.

### Critère
Trois systèmes peuvent traiter le même marché sans se contaminer.

---

## 15. Batch 12 — Dashboard V1

### Ecrans minimum
- état système ;
- capital ;
- positions ;
- décisions ;
- coût IA ;
- PnL ;
- drawdown ;
- agents ;
- événements sécurité.

---

## 16. Batch 13 — Exchange Adapter PAPER/Market Data réel

Le choix de l’exchange doit être figé avant ce lot.

Contenu :
- market data réel ;
- symbol metadata ;
- rate limits ;
- reconnection ;
- tests d’intégration.

---

## 17. Batch 14 — LIVE Broker sécurisé

Pré-requis :
- API key dédiée ;
- retraits désactivés ;
- Risk Engine validé ;
- kill switch ;
- réconciliation.

Ce batch n’active pas automatiquement le LIVE.

---

## 18. Batch 15 — Activation LIVE 100 €

Activation contrôlée du profil Balanced.

**État : livré comme infrastructure/garde-fous fail-closed. Aucun premier ordre réel n’est inclus dans la validation du batch.**

Avant activation :
- checklist sécurité ;
- seuils exacts ;
- tests paper ;
- observation.

---

## 19. Batch 16 — Backtesting & Historical Replay

### Objectif
Construire le banc d’essai historique end-to-end avant tout premier ordre LIVE réel.

### Contenu
- `HistoricalReplayRunner` et `ReplayClock` ;
- datasets historiques versionnés/référencés ;
- réutilisation Feature Engine + Scanner de production ;
- orchestration agents sur données as-of ;
- Risk Engine identique au chemin PAPER ;
- capital/PortfolioRiskState évolutifs ;
- cycle de vie des positions avec stops/targets ;
- modèle de fills historique avec frais/slippage ;
- politique déterministe d’ambiguïté intrabar ;
- equity curve et résultats Evaluation ;
- modes IA MOCK/CACHED/LIVE_EVAL ;
- out-of-sample ;
- walk-forward V1 ;
- exports de runs reproductibles ;
- tests anti-look-ahead.

### Critère
Une période historique peut être rejouée de bout en bout de façon reproductible sans donnée future, avec résultats, coûts, positions et métriques audités.

### Gate
Le LIVE reste non armé tant que ce batch et les validations associées ne sont pas satisfaits.

---

## 20. Batch 17 — Rio / Denver avancés

Selon disponibilité des données :
- dérivés ;
- statistiques historiques issues du moteur Batch 16 ;
- setup DB ;
- outils statistiques réels pour Denver.

Denver ne doit pas inventer des probabilités ou statistiques absentes.

---

## 21. Batch 18 — Réputation et ablation

- réputation multidimensionnelle ;
- tests d’ablation sur datasets/runs comparables ;
- états ON_DEMAND/SHADOW/PROBATION ;
- analyses marginales.

---

## 22. Batch 19 — Recruitment Engine

- propositions ;
- candidat SHADOW ;
- budget candidat ;
- critères de promotion ;
- limites population ;
- passage obligatoire par replay/backtest/PAPER/SHADOW selon pertinence.

---

## 23. Batch 20 — Task Force Agents

- agents temporaires ;
- expiration ;
- mission ;
- budget ;
- allowlist tools.

---

## 24. Batch 21 — Master Portfolio Layer

Plus tard :
- plusieurs crews LIVE ;
- Master Professor ;
- Master Risk Engine ;
- allocation.

---

## 25. Décisions nécessaires par étape

| Décision | Dernier moment recommandé |
|---|---|
| Version Python | Batch 01 |
| Base locale | Batch 01 |
| Exchange | avant Batch 13 |
| Spot/dérivés | résolu pour premier LIVE : Kraken Spot / EUR (Batch 14) |
| Timeframes | bloqueur avant preflight/premier LIVE |
| Balanced risk | bloqueur avant preflight/premier LIVE |
| AI routing | avant Batch 06 |
| Dashboard stack | implémentation Batch 12 |
| Backtest fill/intrabar policy | Batch 16 |
| Critères OOS / walk-forward | Batch 16 |
| Hébergement | avant fonctionnement 24/7 |

---

## 26. Priorités

Ordre :
1. fiabilité ;
2. sécurité ;
3. observabilité ;
4. reproductibilité ;
5. qualité de décision ;
6. coût IA ;
7. performance ;
8. sophistication.

---

## 27. Règle de modification

Si le développement révèle qu’un batch est trop gros :
- le scinder ;
- ne pas compresser artificiellement plusieurs features ;
- mettre à jour cette roadmap et le changelog.

---

## 28. Prochaine action

1. Fusionner l’alignement documentaire post-Batch 15.
2. Démarrer **Batch 16 — Backtesting & Historical Replay** sur la baseline `40c4144` (ou son descendant documentaire uniquement).
3. Garder le LIVE non armé pendant le développement et la validation du Batch 16.
4. Après Batch 16, exécuter les gates historiques puis poursuivre PAPER/SHADOW avant toute décision de premier ordre réel.
