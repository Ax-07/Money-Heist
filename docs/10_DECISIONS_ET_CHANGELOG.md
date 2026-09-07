# Money Heist — Décisions et Changelog

**Document :** Journal des décisions d’architecture et évolutions de documentation  
**Version :** 0.2  
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

## 4. Décisions ouvertes

### OPEN-001 — Version Python
**Résolue par ADR-016.**

### OPEN-002 — Base locale V1
**Résolue par ADR-018.**

### OPEN-003 — Gestionnaire de dépendances
**Résolue par ADR-017.**

### OPEN-004 — Exchange initial
À décider avant le connecteur de données réel.

### OPEN-005 — Spot ou dérivés
À décider avant la finalisation du Risk Engine LIVE.

### OPEN-006 — Timeframes initiaux
À décider avant scanner production.

### OPEN-007 — Limites numériques Balanced
À décider avant Risk Engine final.

### OPEN-008 — Routage modèles IA
À décider avant AI Gateway final.

### OPEN-009 — Stack dashboard
À décider avant Dashboard V1.

### OPEN-010 — Environnement 24/7
À décider avant exploitation continue.

---

## 5. Changelog documentation

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
