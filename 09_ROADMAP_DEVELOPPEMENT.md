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

**État : livré après validation du lot final.**

### Objectif atteint
Fournir le banc d’essai historique end-to-end exigé avant tout premier ordre LIVE réel.

### Contenu livré
- `HistoricalReplayRunner` et `ReplayClock` ;
- datasets historiques content-addressed/versionnés ;
- Feature Engine + Scanner de production réutilisés sans logique parallèle ;
- orchestration agents as-of ;
- Risk Engine identique au chemin PAPER ;
- `PortfolioRiskState` dynamique ;
- cycle de vie positions, stops/targets, fees/slippage ;
- policy intrabar conservatrice STOP_FIRST et gestion des gaps ;
- equity curve + Batch 10 Evaluation ;
- modes IA MOCK/CACHED/LIVE_EVAL ;
- fingerprint business et manifeste de run ;
- `code_version`, `execution_model_version`, seed dans l’identité du run ;
- périodes DESIGN / VALIDATION / OOS ;
- walk-forward V1 sans optimiseur ;
- exports JSON/CSV déterministes ;
- tests anti-look-ahead et frontière anti-LIVE.

### Critère d’infrastructure
Une période historique peut être rejouée de bout en bout de manière reproductible sans donnée future, en conservant les décisions Risk, positions, coûts, equity et métriques.

### Gate opérationnelle
Le batch livré permet d’exécuter la gate mais **ne la déclare pas automatiquement réussie**. Les datasets réels, critères d’acceptation OOS/walk-forward et campagnes PAPER/SHADOW doivent encore être exécutés/validés avant un premier ordre réel.

---


### Extension 16.7 — Backtest Dashboard

**État : livré après validation de l'overlay 16.7.**

- page `/dashboard/backtest` ;
- import/preview CSV historique ;
- lancement DESIGN/VALIDATION/OOS ;
- walk-forward V1 optionnel ;
- configuration PAPER, Risk et modes IA ;
- cache IA V2 exportable/importable ;
- résultats et exports Batch 16 ;
- aucune capacité de trading LIVE.


## 20. Batch 17 — Rio / Denver avancés

### Batch 17a — Denver avancé + infrastructure commune — livré

Contenu :
- schémas/prompts/registry Rio et Denver ;
- disponibilité conditionnelle par contexte typé ;
- orchestration jusqu’à cinq spécialistes, MINI_CREW toujours limité à deux ;
- catalogue content-addressed de statistiques de setup issu de Batch 16 ;
- `as_of` anti-look-ahead et provenance runs/datasets ;
- provider déterministe Denver ;
- support MOCK avancé sans changement du comportement legacy lorsque Rio/Denver sont absents.

Denver ne calcule ni n’invente les statistiques dans le LLM.

### Batch 17b — Rio avec vraies données dérivées — livré

Contenu livré :
- Kraken Futures Analytics public, sans credentials ;
- funding, open interest, variation OI et long/short ratio ;
- mapping explicite spot EUR → perpetual Kraken ;
- cache/fraîcheur/cooldown fail-closed pour Rio ;
- refresh sidecar PAPER/SHADOW non critique ;
- composition de contextes Rio + Denver ;
- observabilité explicite de disponibilité Rio ;
- aucune invention de split long/short des liquidations.

Le replay historique Rio reste séparé et exigera un dataset dérivés historique reproductible.

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

1. Exécuter des campagnes Batch 16 sur des datasets historiques réels et versionnés.
2. Définir avant observation finale les critères quantitatifs DESIGN/VALIDATION/OOS/walk-forward.
3. Poursuivre PAPER/SHADOW et conserver le LIVE non armé tant que la gate n’est pas satisfaite.
4. Démarrer **Batch 18 — Réputation et ablation** afin de mesurer la valeur marginale réelle des spécialistes, dont Rio et Denver.

<!-- BATCH18A_STEP4_ROADMAP_START -->

## Addendum Batch 18a — Fondations réputation et ablation livrées

Le sous-batch 18a est livré avec :
- comparaison d’ablation déterministe sur runs comparables ;
- agrégation et réputation multidimensionnelle ;
- politique advisory de recommandation d’état avec seuils injectés ;
- bridge OOS-only réputation/ablation vers `AgentStateEvidence` ;
- provenance et fingerprint d’audit déterministes ;
- exports publics de la couche Evaluation ;
- aucune mutation automatique des états agents et aucun impact LIVE.

Cette livraison fournit l’infrastructure de preuve du Batch 18. Elle ne constitue pas, à elle
seule, une validation empirique d’un agent : les campagnes comparables réelles et les seuils
opérateur
pré-définis restent nécessaires avant toute décision organisationnelle.

<!-- BATCH18A_STEP4_ROADMAP_END -->

<!-- BATCH18B_STEP4_ROADMAP_START -->

## Addendum Batch 18b — Batch 18 terminé

Le Batch 18 est désormais livré en deux sous-batches :
- 18a : réputation multidimensionnelle, ablation comparative, policy advisory et provenance ;
- 18b : planification déterministe, exécution baseline/twins, runtime PAPER isolé et exports.

La campagne peut produire des preuves comparables par agent sur DESIGN/VALIDATION/OOS, mais les
changements d'état restent advisory-only, soumis aux seuils opérateur pré-définis
et sans mutation
automatique du registry. Le Risk Engine reste autoritaire et aucun chemin LIVE n'est ajouté.

La prochaine étape de roadmap peut donc être **Batch 19 — Recruitment Engine**,
en réutilisant les
preuves de réputation/ablation du Batch 18 au lieu d'un score opaque ou d'un simple rendement.

<!-- BATCH18B_STEP4_ROADMAP_END -->
