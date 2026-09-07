# Money Heist — Décisions et Changelog

**Document :** Journal des décisions d’architecture et évolutions de documentation  
**Version :** 0.4  
**Statut :** Actif

---

## 1. Objectif

Ce fichier évite de perdre les décisions prises au fil des conversations et du développement.

Chaque décision importante doit inclure :
- date ;
- statut ;
- décision ;
- justification ;
- conséquences ;
- éventuelles alternatives.

---

## 2. Statuts

```text
PROPOSED
ACCEPTED
SUPERSEDED
REJECTED
```

---

## 3. Décisions enregistrées

### ADR-001 — Architecture multi-agents Money Heist

**Statut :** ACCEPTED

**Décision :**  
Le système utilise une crew multi-agents orchestrée par The Professor.

**Raison :**
Permettre spécialisation, contradiction et mesure de contribution.

**Conséquence :**
Le code doit prévoir un registre d’agents et un orchestrateur.

---

### ADR-002 — Risk Engine déterministe

**Statut :** ACCEPTED

**Décision :**  
Le Risk Engine n’est pas un agent discrétionnaire.

**Raison :**
Les limites de sécurité ne doivent pas dépendre d’un LLM.

**Conséquence :**
Aucune proposition IA ne peut contourner le Risk Engine.

---

### ADR-003 — Capital initial

**Statut :** ACCEPTED

**Décision :**
Capital LIVE initial prévu : **100 €**.

**Raison :**
Valider l’exécution réelle avec exposition limitée.

---

### ADR-004 — Budget IA prototype

**Statut :** ACCEPTED

**Décision :**
Budget IA externe initial cible : **20 à 30 €**.

**Raison :**
La phase prototype est une phase R&D ; l’autofinancement n’est pas exigé immédiatement.

---

### ADR-005 — Objectif d’autofinancement

**Statut :** ACCEPTED

**Décision :**
Le système doit mesurer sa capacité à couvrir ses coûts IA à terme.

**Restriction :**
Il ne peut pas augmenter ses limites de risque afin d’atteindre cet objectif.

---

### ADR-006 — Un seul système LIVE initial

**Statut :** ACCEPTED

**Décision :**
Un seul système utilisera les 100 € LIVE au départ.

Les autres profils fonctionneront en SHADOW.

---

### ADR-007 — Profils de risque

**Statut :** ACCEPTED

**Décision :**
Prévoir au minimum :
- Conservative / Vault ;
- Balanced ;
- Aggressive / Tokyo.

**Note :**
Les valeurs numériques ne sont pas encore fixées.

---

### ADR-008 — Balanced candidat LIVE

**Statut :** ACCEPTED

**Décision :**
Le profil Balanced est le candidat initial pour le LIVE.

---

### ADR-009 — Recrutement contrôlé

**Statut :** ACCEPTED

**Décision :**
La crew pourra proposer/créer de nouveaux agents spécialistes.

**Restrictions :**
- SHADOW obligatoire au départ ;
- aucun secret ;
- aucune autorité LIVE automatique ;
- budget limité ;
- promotion réversible.

---

### ADR-010 — Agents Core non supprimables automatiquement

**Statut :** ACCEPTED

**Décision :**
Les fonctions Core restent obligatoires :
- orchestration ;
- contradiction ;
- Risk Engine ;
- contrôle coûts ;
- audit.

---

### ADR-011 — Documentation en français

**Statut :** ACCEPTED

**Décision :**
La documentation du projet est rédigée en français.

Les termes techniques standards peuvent rester en anglais lorsque cela améliore la précision.

---

### ADR-012 — Limite documentaire

**Statut :** ACCEPTED

**Décision :**
La documentation permanente doit rester fortement consolidée afin de respecter la limite d’environ 25 sources disponibles.

**Cible :**
Environ 10 documents principaux.

---

### ADR-013 — Livraison du code

**Statut :** ACCEPTED

**Décision :**
ChatGPT fournit le code par lots ZIP intégrables dans VS Code.

Chaque lot contient :
- code ;
- tests ;
- instructions ;
- changelog.

---

### ADR-014 — PAPER/SHADOW avant LIVE

**Statut :** ACCEPTED

**Décision :**
Aucune activation LIVE avant validation du pipeline PAPER et des garde-fous.

---

### ADR-015 — Pas d’accès retrait

**Statut :** ACCEPTED

**Décision :**
Les clés de trading LIVE ne doivent pas disposer de droits de retrait.

---

### ADR-016 — Version Python Batch 01

**Date :** 2026-09-07  
**Statut :** ACCEPTED

**Décision :**
Le projet cible **Python >=3.13,<3.14** pour les premiers lots.

**Raison :**
Privilégier une branche Python récente mais déjà mature afin de réduire le risque de
compatibilité avec les futures dépendances data/trading.

**Conséquence :**
Toute hausse de version Python devra être testée et enregistrée comme décision explicite.

---

### ADR-017 — Gestion des dépendances avec uv

**Date :** 2026-09-07  
**Statut :** ACCEPTED

**Décision :**
Utiliser **uv** avec `pyproject.toml`. Le `uv.lock` est généré lors du premier `uv sync` réussi puis doit être conservé dans le dépôt local.

**Raison :**
Workflow simple et, une fois le lock généré, installation reproductible et support multiplateforme adapté à une
livraison par ZIP intégrée dans VS Code.

**Conséquence :**
Les commandes de référence deviennent `uv sync` et `uv run ...`.

---

### ADR-018 — Base locale SQLite + SQLAlchemy/Alembic

**Date :** 2026-09-07  
**Statut :** ACCEPTED

**Décision :**
La base locale de la V1 démarre avec **SQLite**, via **SQLAlchemy 2.x** et des migrations
**Alembic** versionnées.

**Raison :**
Réduire la complexité opérationnelle du prototype sans coupler le domaine à la base.

**Conséquence :**
Batch 01 accepte uniquement les URLs SQLite. Une migration vers PostgreSQL reste possible
plus tard grâce à la séparation `domain` / `storage`.

---

### ADR-019 — Exchange initial Market Data : Kraken Spot public / EUR

**Date :** 2026-09-07  
**Statut :** ACCEPTED

**Décision :**
Le premier adaptateur de données de marché réelles utilise les endpoints publics **Kraken Spot REST**, sans authentification. L'univers initial de l'adaptateur est `BTC/EUR`, `ETH/EUR` et `SOL/EUR`.

Cette décision concerne le **Market Data du Batch 13**. Elle n'active aucun ordre réel et ne décide pas à elle seule du produit ou du mode du futur Batch 14/15.

**Raison :**
- endpoints publics pour trades horodatés, OHLC et métadonnées de paires ;
- `AssetPairs` fournit les contraintes nécessaires au prototype (`tick_size`, précision prix/quantité, `ordermin`, `costmin`) ;
- quote EUR cohérente avec le capital prototype exprimé en euros ;
- aucune clé API ni SDK exchange requis pour le Batch 13 ;
- séparation simple entre payload Kraken brut et modèles Money Heist existants.

**Conséquences :**
- le prix courant du Batch 13 provient du dernier trade public horodaté, et non du ticker non horodaté ;
- la dernière ligne OHLC Kraken est conservée avec `is_closed=False` ;
- les métadonnées sont projetées vers `MarketConstraints` sans modifier le Risk Engine ;
- les timeframes et seuils de fraîcheur opérationnels restent explicitement injectés et ne sont pas figés par cette ADR ;
- aucune capacité LIVE, clé de trading ou permission de retrait n'est ajoutée.

**Alternatives considérées :**
- Binance Spot : API publique riche et métadonnées détaillées, mais non retenue comme premier adaptateur du prototype ;
- autres exchanges : restent compatibles avec l'architecture par ajout d'adaptateurs futurs.

---

### ADR-020 — Premier marché LIVE : Kraken Spot / EUR

**Date :** 2026-09-07  
**Statut :** ACCEPTED

**Décision :**
Le premier chemin d’exécution LIVE cible **Kraken Spot / EUR**, avec l’univers initial `BTC/EUR`, `ETH/EUR`, `SOL/EUR` et le système `balanced_v1`.

Le premier LIVE n’ajoute pas de marge, dérivés ou levier et refuse les entrées SHORT.

**Raison :**
Réduire la surface de risque du prototype et rester cohérent avec le Market Data Kraken/EUR déjà livré.

**Conséquence :**
`OPEN-005` est résolue pour le premier LIVE. Les dérivés restent une extension future, notamment pour Rio.

---

### ADR-021 — Activation LIVE Batch 15 fail-closed

**Date :** 2026-09-07  
**Statut :** ACCEPTED

**Décision :**
Le Batch 15 fournit la couche d’activation opérationnelle sans envoyer d’ordre réel pendant le développement/tests.

Le cycle est :

```text
LIVE_DISABLED → LIVE_PREFLIGHT → LIVE_ARMED
```

L’armement est explicite, éphémère et perdu au redémarrage. Les credentials seuls sont insuffisants. Les paramètres Balanced incomplets, timeframes inconnus ou seuils de fraîcheur inconnus restent bloquants au lieu d’être inventés.

**Conséquence :**
La livraison du Batch 15 ne doit jamais être interprétée comme « le système peut maintenant trader automatiquement les 100 € ».

---

### ADR-022 — Backtesting & Historical Replay avant premier ordre réel

**Date :** 2026-09-07  
**Statut :** ACCEPTED

**Décision :**
Insérer **Batch 16 — Backtesting & Historical Replay** avant tout premier ordre LIVE réel.

La gate de validation devient :

```text
Replay historique
→ Backtest end-to-end
→ Validation hors échantillon
→ Walk-forward
→ PAPER / SHADOW
→ Preflight LIVE
→ Petit capital réel
```

Le précédent Batch 16 Rio/Denver est décalé en Batch 17 ; les anciens Batchs 17 à 20 deviennent respectivement 18 à 21.

**Raison :**
Le code post-Batch 15 possède l’import historique, le replay scanner, le Paper Broker, le pipeline PAPER et Evaluation, mais pas encore la boucle historique end-to-end avec capital évolutif, cycle de vie des positions, OOS et walk-forward.

**Conséquences :**
- le LIVE reste non armé pendant Batch 16 ;
- Denver avancé pourra consommer de vraies statistiques produites par le moteur historique ;
- toute validation de prompts/agents devra identifier dataset, versions et mode IA ;
- l’ablation avancée reste dans le batch suivant Rio/Denver conformément à la roadmap réalignée.

---

### ADR-023 — GitHub comme référence intégrée et synchronisation des sources projet

**Date :** 2026-09-07  
**Statut :** ACCEPTED

**Décision :**
Le dépôt GitHub **`Ax-07/Money-Heist`**, branche `main`, constitue la référence de l’état intégré du code et des dix documents permanents.

Les copies de ces documents chargées comme sources du projet ChatGPT doivent être remplacées après une révision documentaire approuvée afin d’éviter qu’une nouvelle conversation reparte d’une spécification obsolète.

**Raison :**
Après les Batchs 01 à 15, certaines sources initiales décrivaient encore le projet comme pré-développement et conservaient une roadmap devenue obsolète.

**Conséquences :**
- une mise à jour documentaire significative est commitée dans GitHub ;
- les dix sources ChatGPT sont ensuite rafraîchies avec les mêmes versions ;
- en cas de divergence temporaire, GitHub `main` prévaut pour l’état intégré ;
- les ZIP restent un moyen de livraison possible mais ne remplacent pas l’historique Git intégré.

---

## 4. Décisions ouvertes

### OPEN-001 — Version Python
**Résolue par ADR-016.**

### OPEN-002 — Base locale V1
**Résolue par ADR-018.**

### OPEN-003 — Gestionnaire de dépendances
**Résolue par ADR-017.**

### OPEN-004 — Exchange initial
**Résolue par ADR-019 pour le Market Data initial : Kraken Spot public / EUR.**

### OPEN-005 — Spot ou dérivés
**Résolue pour le premier LIVE par ADR-020 : Kraken Spot / EUR.** Les dérivés restent hors périmètre initial.

### OPEN-006 — Timeframes initiaux
Toujours ouverte. **Bloque le preflight/premier LIVE** tant que les timeframes de production ne sont pas validés explicitement.

### OPEN-007 — Limites numériques Balanced
Toujours ouverte. **Bloque le preflight/premier LIVE** tant qu’un profil Balanced complet et validé n’est pas fourni explicitement.

### OPEN-008 — Routage modèles IA
L’infrastructure de routage a été livrée au Batch 06. La configuration de modèles utilisée pour les expériences/backtests reste versionnée et explicite ; ce point n’est plus un prérequis de construction du Gateway.

### OPEN-009 — Stack dashboard
Le Dashboard V1 a été livré au Batch 12. Le choix technique effectif est désormais porté par l’implémentation ; ce point n’est plus un bloqueur de roadmap.

### OPEN-010 — Environnement 24/7
À décider avant exploitation continue.

---

## 5. Changelog documentation

### v0.4 — 2026-09-07 — Alignement post-Batch 15
- documentation source réalignée sur l’état réel des Batchs 01 à 15 ;
- ADR-020 : premier LIVE Kraken Spot / EUR, sans dérivés/marge/levier et sans entrée SHORT ;
- ADR-021 : activation Batch 15 fail-closed, armement opérateur éphémère ;
- ADR-022 : Batch 16 Backtesting & Historical Replay inséré avant tout premier ordre réel ;
- roadmap décalée : Rio/Denver → 17, Réputation/Ablation → 18, Recruitment → 19, Task Force → 20, Master Portfolio → 21 ;
- OPEN-005 résolue pour le premier LIVE ;
- OPEN-006 et OPEN-007 explicitement conservées comme bloqueurs LIVE ;
- ADR-023 : GitHub `main` devient la référence intégrée et les sources ChatGPT doivent être synchronisées après les mises à jour documentaires.

### v0.3 — 2026-09-07
- démarrage du Batch 13 — Exchange Adapter PAPER / Market Data réel ;
- ADR-019 : Kraken Spot public / EUR retenu pour le premier adaptateur Market Data ;
- OPEN-004 marquée comme résolue pour le Market Data initial ;
- OPEN-005 reste ouverte pour la décision finale spot/dérivés avant LIVE.

### v0.2 — 2026-09-07
- démarrage du Batch 01 — Fondations ;
- ADR-016 : Python 3.13 ;
- ADR-017 : uv ;
- ADR-018 : SQLite + SQLAlchemy/Alembic ;
- OPEN-001, OPEN-002 et OPEN-003 marquées comme résolues.

### v0.1
- création de la structure documentaire détaillée ;
- ajout architecture ;
- ajout système agents ;
- ajout trading/risque ;
- ajout market data/exécution ;
- ajout évaluation/apprentissage ;
- ajout sécurité/opérations ;
- ajout API/modèles ;
- ajout roadmap ;
- ajout journal de décisions.

---

## 6. Règle d’entretien

Lorsqu’une décision ouverte devient ferme :
1. ajouter/mettre à jour l’ADR ;
2. mettre à jour le document thématique ;
3. si nécessaire mettre à jour `01_PROJECT_MASTER.md` ;
4. ajouter une entrée de changelog.

Le journal ne doit pas devenir une copie complète des autres documents.
