# Money Heist — Décisions et Changelog

**Document :** Journal des décisions d’architecture et évolutions de documentation
**Version :** 1.1
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
Le dépôt GitHub **`Ax-07/Money-Heist`**, branche `main`, constitue la référence de l’état intégré du code et des onze documents permanents.

Les copies de ces documents chargées comme sources du projet ChatGPT doivent être remplacées après une révision documentaire approuvée afin d’éviter qu’une nouvelle conversation reparte d’une spécification obsolète.

**Raison :**
Après les Batchs 01 à 15, certaines sources initiales décrivaient encore le projet comme pré-développement et conservaient une roadmap devenue obsolète.

**Conséquences :**

- une mise à jour documentaire significative est commitée dans GitHub ;
- les onze sources ChatGPT sont ensuite rafraîchies avec les mêmes versions ;
- en cas de divergence temporaire, GitHub `main` prévaut pour l’état intégré ;
- les ZIP restent un moyen de livraison possible mais ne remplacent pas l’historique Git intégré.

---

### ADR-024 — Contrat de reproductibilité et validation historique Batch 16

**Date :** 2026-09-08
**Statut :** ACCEPTED

**Décision :**
Le moteur historique Batch 16 est PAPER-only et ses expériences doivent être identifiables/reproductibles.

Un `BacktestRun` inclut dans son identité :

- dataset/version/hash ;
- période ;
- configuration de risque et d’exécution ;
- versions Feature/Scanner/Risk/Prompts/Models ;
- `code_version` ;
- `execution_model_version` ;
- `random_seed` ;
- mode IA.

Les validations finales séparent explicitement `DESIGN`, `VALIDATION` et `OOS`. Le walk-forward V1 roule ces trois fenêtres avec une configuration figée et ne contient pas d’optimiseur automatique.

Les ambiguïtés intrabar sans données plus fines utilisent `STOP_FIRST`. Les gaps défavorables au stop partent du prix d’ouverture avec slippage PAPER ; les gaps favorables au target sont plafonnés au target. Le target V1 ferme la position entière au premier target atteint.

`LIVE_EVAL` autorise uniquement un fournisseur IA réel via Batch 06 ; l’exécution reste `PaperTradingPipeline`/`PaperBroker`. Le package backtest ne dépend pas de `app.trading.live`.

**Raison :**
Une comparaison historique n’est exploitable que si dataset, code, modèles, prompts, hypothèses d’exécution et seed sont explicitement traçables. La séparation OOS et l’absence d’optimiseur V1 limitent le risque d’overfitting implicite.

**Conséquences :**

- changer une version matérielle ou le seed change le `run_id` ;
- les rapports OOS restent séparés ;
- les exports incluent un manifeste et un fingerprint business ;
- le moteur historique ne peut jamais armer le LIVE ;
- les critères numériques de promotion restent une décision opérateur/projet à définir avant les tests finaux.

---

### ADR-025 — Backtest Dashboard PAPER-only et cache IA V2

**Date :** 2026-09-08
**Statut :** ACCEPTED

**Décision :**
Le Batch 16.7 expose le moteur historique via `/dashboard/backtest`. Le Dashboard construit des runtimes historiques isolés utilisant `PaperTradingPipeline`, `RiskEngine` et `PaperBroker`; il n'introduit aucun chemin d'ordre LIVE.

La clé OpenAI éventuelle de `LIVE_EVAL` est fournie uniquement via `OPENAI_API_KEY` dans l'environnement backend. Aucun secret fournisseur n'est accepté par le formulaire ou les modèles API du Dashboard.

Le cache IA passe au schéma `money-heist.backtest-ai-cache.v2`. La clé exclut le `request_id` volatil et son scope d'expérience ignore le seul champ `ai_mode`, afin de permettre `LIVE_EVAL → CACHED` pour la même expérience matérielle.

**Conséquences :**

- le Dashboard V1 SHADOW reste read-only ;
- la nouvelle UI peut lancer des simulations mais jamais armer le LIVE ;
- les contraintes marché et limites Risk restent explicites ;
- un cache miss `CACHED` échoue fail-closed ;
- les campagnes officielles doivent remplacer `batch16.7-working-tree` par un `code_version` immuable.

### ADR-026 — Recruitment lifecycle séparé, OOS et advisory-only

**Date :** 2026-09-09
**Statut :** ACCEPTED

**Décision :**
Le Batch 19 possède un lifecycle candidat propre (`PROPOSED`, `CANDIDATE`, `SHADOW`, `PROBATION`, `REJECTED`, `PROMOTION_RECOMMENDED`) séparé de `AgentState`. Un candidat Recruitment n'est pas automatiquement ajouté à `AgentRegistry`.

Les critères de succès sont pré-enregistrés dans le CandidateSpec et exigent une preuve OOS pour l'advisory de promotion. Les campagnes candidates réutilisent le Historical Replay/PAPER Batch 16 et les comparaisons/réputation Batch 18. Les seuils de population et de budget sont des politiques opérateur explicites.

L'advisory peut seulement produire `REJECT`, `EXTEND`, `PROBATION` ou `RECOMMEND_PROMOTION`. Le planning de transition reste soumis à autorisation opérateur; les audits deviennent `STALE` si le contexte matériel change. L'API HTTP Recruitment V1 est read-only (`GET /api/recruitment/capabilities`).

**Conséquences :**

- pas de nouvel état `CANDIDATE` dans `AgentState` ;
- pas de mutation automatique du registre ;
- pas de promotion directe vers `ACTIVE`/`ON_DEMAND` ;
- pas de second moteur de backtest ou d'ablation ;
- pas de seuil de promotion caché ou inventé après observation ;
- pas d'autorité LIVE via Recruitment ;
- décisions et plans reproductibles/fingerprintés.

### ADR-027 — Task Force temporaire registry-only, operator-gated et advisory-only

**Date :** 2026-09-09
**Statut :** ACCEPTED

**Décision :**
Le Batch 20 implémente les Task Forces comme compositions temporaires d’agents déjà présents dans
`AgentRegistry`. Elles possèdent une mission étroite, une expiration, des policies explicites de
population/coût/appels/retries et une allowlist tools bornée par le registre.

La composition est déterministe et peut utiliser les preuves de réputation multidimensionnelles
Batch 18 sans score magique. Toute exécution exige un lifecycle approuvé par l’opérateur, une gate
Task Force et le hard budget du Batch 06 AI Gateway.

L’agrégation conserve la provenance et n’effectue aucun vote sémantique ou moyenne de confiance. Le
rapport Task Force peut être injecté comme source grounded du Professor final, sans être transmis au
Palermo principal ni contourner le pipeline existant.

L’évaluation historique compare `BASELINE` et `WITH_TASK_FORCE` sur des runtimes PAPER isolés et
scelle les résultats par fingerprints/audit `FRESH / STALE`.

**Conséquences :**

- un candidat Recruitment absent du registre n’est pas sélectionnable ;
- aucune Task Force ne crée ou promeut automatiquement un agent ;
- aucun provider IA n’est appelé hors AI Gateway ;
- aucun rapport Task Force ne crée directement de `TradeProposal` ;
- Palermo principal et le Risk Engine déterministe restent des frontières séparées ;
- aucune autorité LIVE n’est dérivée d’une autorisation Task Force ;
- les preuves économiques marginales nécessitent des twins replay comparables.

### ADR-028 — Validation technique LIVE_EVAL séparée de la preuve statistique

**Date :** 2026-09-11
**Statut :** ACCEPTED

**Décision :**
Le Batch 16 possède désormais un smoke LIVE_EVAL end-to-end de référence sur le commit
`294cfa2547f94c9694fdc65758c3f9435ff55dd2`, campagne `177add07-b684-440c-b8ca-a37313a6eac5`,
dataset `BTC/USDC:1h:4f5515aef296533f`.

Le smoke a traité `345/345` unités de travail et 15 opportunités sans échec technique. Le Professor
a produit 14 `NO_TRADE` et 1 `SHORT`. La proposition SHORT a atteint le Risk Engine déterministe,
qui l’a `RESIZED` à `0.00156 BTC`, notionnel `99.4993740`, risque approuvé `0.7306260`, avant un
ordre PAPER.

**Décision de gouvernance :**
Cette preuve ferme la validation **technique** du chemin LIVE_EVAL historique, mais ne constitue pas
une preuve de performance ou une autorisation LIVE. Les critères DESIGN/VALIDATION/OOS,
walk-forward, multi-régimes, PAPER/SHADOW et les bloqueurs LIVE explicites restent applicables.

**Conséquences :**

- le fournisseur IA réel peut être évalué dans Historical Replay sans ordre LIVE ;
- le Risk Engine reste l’autorité déterministe et peut redimensionner/rejeter une proposition IA ;
- aucun trade n’est forcé pour satisfaire un test ;
- `OPEN-006` et `OPEN-007` restent ouverts ;
- la prochaine phase Batch 16 est une évaluation statistique plus large, pas un nouveau débogage du
  chemin technique.

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

### v0.9 — 2026-09-11 — Validation technique LIVE_EVAL Batch 16

- smoke de référence : `177add07-b684-440c-b8ca-a37313a6eac5` ;
- code version : `294cfa2547f94c9694fdc65758c3f9435ff55dd2` ;
- dataset : `BTC/USDC:1h:4f5515aef296533f` ;
- `345/345`, 15 opportunités, 14 `NO_TRADE`, 1 `SHORT` ;
- Risk Engine `RESIZED` puis 1 ordre PAPER ;
- 0 échec technique ;
- séparation explicite entre validation technique du pipeline et validation statistique/LIVE ;
- ADR-028 ajouté.

### v0.8 — 2026-09-09 — Batch 20 Task Force dynamique

- contrats, lifecycle et gates Task Force temporaires ;
- composition registry-only avec capabilities explicites et réputation Batch 18 ;
- provenance, fingerprints et stale detection ;
- exécution multi-membres exclusivement via AI Gateway et compute gate ;
- agrégation provenance-preserving avec Red Team optionnel ;
- trigger bridge explicite et intégration grounded dans le Professor final ;
- évaluation coût/latence et comparaison économique baseline/treatment ;
- Historical Replay PAPER `BASELINE` / `WITH_TASK_FORCE` ;
- replay seal et audit `FRESH / STALE` ;
- exports publics Task Force/Evaluation/Orchestration ;
- ADR-027 ajouté.

### v0.7 — 2026-09-09 — Batch 19 Recruitment Engine

- lifecycle candidat séparé du registre opérationnel ;
- CandidateSpec gelé avec baseline, budget, allowlist et critères OOS ;
- gates population/fréquence/compute ;
- campagnes twins Historical Replay/PAPER et comparabilité/provenance ;
- bridge vers Batch 18 ablation/réputation ;
- évidence coûts directs/marginaux et paquet auditable ;
- advisory déterministe et planning opérateur-gaté ;
- audit FRESH/STALE et stale-plan guards ;
- exports publics et API GET read-only Recruitment ;
- ADR-026 ajouté.

### v0.6 — 2026-09-08 — Batch 16.7 Backtest Dashboard

- interface `/dashboard/backtest` reliée au moteur Batch 16 ;
- campagnes DESIGN/VALIDATION/OOS et walk-forward optionnel ;
- runtime PAPER/Risk réel depuis l'interface ;
- cache IA V2 compatible `LIVE_EVAL → CACHED` ;
- secrets fournisseur conservés côté backend ;
- ADR-025 ajouté.

### v0.5 — 2026-09-08 — Finalisation Batch 16

- Batch 16 Backtesting & Historical Replay livré ;
- replay end-to-end PAPER avec PortfolioRiskState dynamique et cycle de vie OHLC ;
- policy intrabar STOP_FIRST, gaps, fees/slippage et targets déterministes ;
- intégration Batch 10 Evaluation et modes IA MOCK/CACHED/LIVE_EVAL ;
- fingerprint business, `code_version`, `execution_model_version` et seed ;
- périodes DESIGN/VALIDATION/OOS et walk-forward V1 sans optimiseur ;
- exports déterministes et tests de frontière anti-LIVE ;
- ADR-024 ajouté ;
- documentation réalignée post-Batch 16.

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

<!-- BATCH22_FRONTEND_V2 -->

### ADR-029 — Frontend Money Heist V2 en Next.js

**Date :** 2026-09-12
**Statut :** ACCEPTED

**Décision :**
Le cockpit Frontend V2 utilise Next.js + React + TypeScript strict. Le backend Python/FastAPI reste responsable de la logique métier, du Risk Engine, de l'exécution, des secrets et de la sécurité.

Le chart est abstrait derrière `TradingChartAdapter`. En l'absence de bibliothèque propriétaire TradingView légalement fournie dans le dépôt, la première implémentation utilise TradingView Lightweight Charts.

La baseline ne fournit pas de WebSocket/SSE opérateur ni d'API HTTP sécurisée d'armement LIVE. La V2 utilise donc le polling centralisé et n'ajoute aucun bouton LIVE factice.

**Conséquences :**

- server state via TanStack Query, validation runtime via Zod ;
- Zustand limité aux préférences UI ;
- aucun secret dans le navigateur ou `NEXT_PUBLIC_*` ;
- aucune décision ou statistique de production recalculée côté frontend ;
- le Dashboard V1 reste présent pendant la migration ;
- une évolution temps réel ou TradingView propriétaire reste possible derrière les adapters.

<!-- BATCH22_1_BACKTEST_COCKPIT -->

### ADR-030 — Sidecar durable Frontend V2 pour Historical Replay

**Date :** 2026-09-13
**Statut :** ACCEPTED

Les entrées immuables et sorties déjà produites du Backtest Cockpit sont persistées sous `.money-heist/frontend-v2/`, surchargeable par `MONEY_HEIST_FRONTEND_V2_STORAGE_DIR`. Ce sidecar ne devient jamais un second moteur de backtest et ne recalcule ni Scanner, agents, Risk, fills ni métriques.

<!-- DOC_REALIGN_ADR31_PROMPT_CACHE_START -->

### ADR-031 — OpenAI Prompt Cache explicite et comptabilité des coûts IA

**Date :** 2026-09-15
**Statut :** ACCEPTED

**Décision :**
Le AI Gateway peut utiliser le Prompt Cache explicite OpenAI uniquement lorsqu’une route déclare `PromptCacheCapability.OPENAI_EXPLICIT` et une `PromptCachePolicy` correspondante. Le rendu `money-heist.prompt-transport.v2` sépare un préfixe `developer` stable d’un suffixe `user` dynamique.

La comptabilité distingue input normal, cache read, cache write et output. Evaluation/Lisbon conservent le coût réel et un coût contrefactuel sans cache. Le hard budget réserve le tarif d’entrée le plus défavorable.

Le Prompt Cache fournisseur reste distinct du cache de réponses `money-heist.backtest-ai-cache.v2`. Aucune autorité Risk/LIVE, règle de grounding ou frontière PAPER/SHADOW/LIVE n’est modifiée.

**Document détaillé :** `docs/ADR_031_OPENAI_PROMPT_CACHE_ET_COUTS.md`.

<!-- DOC_REALIGN_ADR31_PROMPT_CACHE_END -->

<!-- DOC_REALIGN_CHANGELOG_20260915_START -->

## Changelog documentation — 2026-09-15

## Alignement documentaire post-Batch 22.1 — 2026-09-15

- état courant réaligné sur `main @ 9f42d3e` ;
- Master Portfolio Layer reflété dans la roadmap/document maître ;
- Frontend V2 / Backtest Cockpit 22.1 et validation pnpm documentés ;
- Prompt Cache OpenAI intégré au corpus permanent et renuméroté ADR-031 pour éviter le conflit avec ADR-026 Recruitment ;
- Market Data utilities `scripts/market_data/` documentés ;
- miroirs racine/`docs/` resynchronisés, notamment `05_MARKET_DATA_ET_EXECUTION.md` ;
- nettoyage des artefacts historiques référencé (`c4ffda0`, `9f42d3e`).

<!-- DOC_REALIGN_CHANGELOG_20260915_END -->

<!-- ADR032_DOCS_SINGLE_SOURCE -->

### ADR-032 — Source documentaire unique sous `docs/`

**Date :** 2026-09-16
**Statut :** ACCEPTED

**Décision :**
Les documents permanents numérotés `00` à `12` sont canoniques uniquement sous `docs/`. Les anciennes
copies racine sont supprimées. `README.md` reste le point d’entrée du dépôt et `docs/README.md`
devient l’index documentaire.

**Raison :**
La duplication racine / `docs/` créait un risque de divergence silencieuse et imposait des tests de
synchronisation sans valeur fonctionnelle.

**Conséquences :**

- une seule copie à maintenir pour chaque document permanent ;
- les tests documentaires lisent `docs/` directement ;
- un test de layout interdit le retour des doublons racine ;
- les documents opérateur transverses (`LIVE_*`, `CHANGELOG_BATCH.md`) restent à la racine.

<!-- ADR033_DECISION_FUNNEL -->

### ADR-033 — Decision Funnel strictement observationnel

**Date :** 2026-09-16
**Statut :** ACCEPTED

**Décision :**
La mesure causale Batch 23A.1 agrège uniquement des sorties déjà produites par Historical Replay / Evaluation. Elle ne déclenche aucun composant décisionnel supplémentaire et n'est jamais injectée dans `DecisionContext`.

Deux compteurs techniques pré-Scanner sont autorisés dans le runner pour distinguer warm-up incomplet et clôtures hors timeframe de décision. Les statistiques postérieures au choix, notamment les trades clôturés, sont explicitement séparées dans `post_hoc`.

**Raison :**
Avant de modifier les seuils du Scanner, les règles du Professor ou les paramètres Risk, il faut pouvoir expliquer quantitativement où les opportunités sont filtrées tout en garantissant l'identité comportementale du replay.

**Conséquences :**

- aucun changement de seuil/prompt/règle d'exécution dans 23A.1 ;
- `DecisionFunnelReport` ne fait pas partie de `BacktestConfig` et ne modifie pas `run_id` ;
- le fingerprint business historique reste indépendant des compteurs d'observation ;
- les reason codes existants sont réutilisés/normalisés plutôt que remplacés ;
- les futurs Forward Outcomes restent post-hoc et ne peuvent pas créer de look-ahead.

**Commit de référence :** `fbec1d3fadaf811c6e84d33741aa08166cc472cd`.

<!-- BATCH23A1_CHANGELOG_CLOSURE -->

## Changelog documentation — 2026-09-16 — Clôture Batch 23A.1

- Batch 23A.1 Decision Funnel Baseline livré et validé ;
- état courant, architecture, contrats API/modèles, roadmap, ADR et documentation Historical Replay réalignés ;
- prochaine étape explicitée : Batch 23A.2 Forward Outcomes ;
- aucune autorité LIVE, règle Risk, seuil Scanner ou prompt agent modifié par cette clôture.

<!-- ADR034_FORWARD_OUTCOMES -->

### ADR-034 — Forward Outcomes strictement post-hoc et bornés par split

**Date :** 2026-09-16
**Statut :** ACCEPTED

**Décision :**
Les Forward Outcomes sont calculés uniquement après la fin du chemin décisionnel de l'observation évaluée. Les horizons H1/H3/H5/H10/H20 sont exprimés dans le timeframe de décision et utilisent le close du `FeatureSnapshot` comme référence.

Un outcome ne peut pas franchir `period_end` du split courant. Un horizon incomplet à cause d'un gap, d'une frontière de période ou des deux ne publie aucune métrique de prix partielle.

**Raison :**
Mesurer le devenir des opportunités sans introduire de look-ahead ni confondre disponibilité historique future et information accessible au moment de la décision.

**Conséquences :**

- aucune donnée Forward Outcomes dans `DecisionContext` ;
- mêmes règles sur DESIGN, VALIDATION et OOS ;
- provenance dataset/run conservée ;
- aucun changement `BacktestConfig`, `run_id`, Scanner, Professor, Risk ou broker.

**Commit de référence :** `b78266efe5c0bf203d75348907cac5000472e9c6`.

<!-- ADR035_FUNNEL_OUTCOME_ATTRIBUTION -->

### ADR-035 — Funnel Outcome Attribution descriptive, sans autorité de tuning

**Date :** 2026-09-16
**Statut :** ACCEPTED

**Décision :**
La couche Funnel Outcome Attribution peut croiser les Forward Outcomes avec les métadonnées déjà émises par le pipeline, mais elle reste strictement descriptive. Elle ne choisit pas un seuil, ne classe pas automatiquement une configuration et ne modifie aucune règle.

Les dimensions multi-valuées telles que triggers, agents sélectionnés et reason codes Risk conservent leur caractère chevauchant.

**Raison :**
Permettre l'analyse de l'endroit où les opportunités sont filtrées et de leur devenir futur sans transformer une corrélation post-hoc en causalité ou en décision de configuration.

**Conséquences :**

- pas de winner automatique ;
- pas de promotion de configuration ;
- les hypothèses de tuning doivent être testées séparément sur VALIDATION/OOS ;
- aucune autorité Risk/LIVE n'est déplacée.

**Commit de référence :** `42903cce9e694fdf1f23923fdba0708176e7775a`.

<!-- ADR036_SCANNER_FORWARD_OUTCOMES -->

### ADR-036 — Scanner Forward Outcomes fondés sur les décisions Scanner réellement émises

**Date :** 2026-09-16
**Statut :** ACCEPTED

**Décision :**
La mesure pré-candidat lit les `ScanResult` déjà produits par Historical Replay et couvre exactement trois classes : `NO_TRIGGER`, `TRIGGER_BELOW_CANDIDATE_THRESHOLD`, `CANDIDATE_OPPORTUNITY`.

Elle conserve le score exact, le `min_priority_score` réellement utilisé et leur marge. Elle réutilise le moteur d'outcomes 23A.2 et ne rappelle jamais le Scanner pour reconstruire une décision.

**Raison :**
Comparer post-hoc ce qui se trouve de part et d'autre du seuil candidat sans modifier ou réinterpréter rétroactivement le comportement qui a réellement eu lieu.

**Conséquences :**

- conservation stricte avec les compteurs Decision Funnel ;
- aucune bande de score arbitraire imposée par la couche de mesure ;
- aucun tuning automatique du seuil ;
- mêmes garanties no-lookahead / split boundary que 23A.2.

**Commit de référence :** `611bef38f9e056ea7d7964a0f10191bac58551e4`.

<!-- BATCH23A2_4_CHANGELOG_CLOSURE -->

## Changelog documentation — 2026-09-16 — Clôture consolidée Batch 23A.2 à 23A.4

- Batch 23A.2 Forward Outcomes livré et validé (`b78266e`) ;
- Batch 23A.3 Funnel Outcome Attribution livré et validé (`42903cc`) ;
- Batch 23A.4 Scanner Forward Outcomes livré et validé (`611bef3`) ;
- état courant, architecture, contrats API/modèles, roadmap et documentation Historical Replay réalignés ;
- pile 23A désormais capable de mesurer du Scanner pré-candidat jusqu'à Risk/exécution avec outcomes post-hoc ;
- aucun seuil Scanner, prompt Professor, paramètre Risk, règle d'exécution ou autorité LIVE modifié ;
- prochaine phase : campagnes longues multi-régimes DESIGN / VALIDATION / OOS avant toute hypothèse de tuning.
<!-- ADR037_ANALYTICS_LAB_OBSERVATION_ONLY -->

### ADR-037 — Analytics Lab Observation-Only Authority Boundary

**Date :** 2026-09-16
**Statut :** ACCEPTED

Le futur Analytics Lab est une dérivation read-only du Historical Replay
canonique. `BacktestRun` et `AnalyticsLabRun` ont des identités distinctes ; les
versions Analytics ne modifient pas le `BacktestRun.run_id` ni le business
fingerprint tant qu'Analytics n'influence aucune décision. `DatasetRef`/MTF
Money Heist restent la seule vérité de marché et Batch 23A reste la vérité
post-hoc canonique. Toute future injection Analytics dans `DecisionContextV1`
devra être traitée comme un batch comportemental distinct.

Voir `docs/ADR_037_ANALYTICS_LAB_OBSERVATION_ONLY.md`.

<!-- BATCH_24A2_RICH_INDICATORS -->

### Décision Batch 24A.2 — séparation Feature Engine / Analytics Indicators

Le Feature Engine de production reste inchangé. Analytics possède un registre indépendant, versionné et fingerprinté. Les divergences ADX (initialisation) et Volume Ratio (inclusion/exclusion de la bougie courante) sont intentionnelles, testées et documentées. Une évolution du registre change l'identité Analytics mais pas l'identité business du backtest.

<!-- BATCH_24A3_TECHNICAL_EVENTS -->

### 2026-09-16 — Batch 24A.3 Technical Events

**ACCEPTED** — Les Technical Events sont des observations Analytics descriptives et non
des signaux de trading. Leur source unique est `AnalyticsIndicatorSnapshot`; le moteur est
stateless T-1/T, causal, déterministe et isolé du Scanner/Decision/Risk/PAPER/LIVE. Les
seuils canoniques V1 sont versionnés dans le registry (RSI 30/50/70, ADX 25, MFI 20/80,
volume ratio 1.5). Les changements matériels de registry modifient l'identité Analytics,
jamais l'identité business du `BacktestRun`.

<!-- BATCH_24A4_CAUSAL_STRUCTURE_ZIGZAG -->

### 2026-09-17 — Batch 24A.4 Causal Structure & ZigZag

**ACCEPTED** — coexistence explicite de la structure Money Heist et d'un ZigZag
Analytics causal. Définition V1 : ATR14 Analytics, reversal 2.0 ATR, seuil inclusif
verrouillé au candidat, initialisation dual-candidate, ambiguïté OHLC conservatrice,
timestamps sur close_time des candles closes.

<!-- BATCH_24A5_PATTERNS_CAUSAL_LIFECYCLE -->

## Batch 24A.5 — Patterns & Causal Lifecycle

- registry expérimental versionné de 12 patterns adapté de P5.v2 ;
- source primaire de pivots `CAUSAL_ZIGZAG` via contrat source-agnostic `PatternPivot` ;
- lifecycle causal `FORMING / CONFIRMED / FAILED / INVALIDATED` ;
- `detected_at` distinct de l'origine géométrique et aucune back-propagation du statut final ;
- breakout/invalidation sur clôture, policy intrabar conservatrice ;
- IDs stables, state fingerprints évolutifs, provenance des pivots conservée ;
- intégration `AnalyticsSnapshot` et `pattern_registry_version` ;
- observation-only : aucun impact Scanner/DecisionContext/Agents/Risk/PAPER/LIVE/Forward Outcomes ;
- calibration et comparaison de sources réservées au Batch 24A.6.

<!-- BATCH_24A6_PATTERN_CALIBRATION -->

## Batch 24A.6 — Pattern Calibration & Pivot-Source Diagnostics

- calibration observation-only, sans Forward Outcomes ni autorité trading ;
- instrumentation du Pattern Engine canonique : candidats acceptés/rejetés, rule IDs,
  observed/required et raisons ordonnées ;
- identité candidat déterministe, indépendante de P&L/futur ;
- comparaison `CAUSAL_ZIGZAG` vs `MONEY_HEIST_STRUCTURE` avec Pattern Registry constant ;
- adapter Analytics causal pour les strict pivots Money Heist, sans modifier
  `app/market/structure.py` ;
- rapports séparés du `AnalyticsSnapshot`, avec `PatternCalibrationRun` dérivé de
  `AnalyticsLabRun` ;
- DESIGN/VALIDATION/OOS conservés ; acceptance ratio != trading win rate ;
- aucun ranking, auto-tuning, frontend, Contexts/Sequences ou modification des seuils 24A.5.

<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->

### 2026-09-17 — Batch 24A.7 Causal Contexts & Sequences

**ACCEPTED (candidate pending local validation)** — Contexts et Sequences deviennent une couche Research séparée de `DecisionContextV1`. Anchors v1 : Technical Event, Pattern Transition, ZigZag Pivot confirmé. Conditions : Indicator/Event/Pattern/Structure/ZigZag. `THEN` est strict (same-bar rejeté), les fenêtres sont en barres avec borne N incluse, le matching choisit le prédécesseur compatible le plus récent, les partials et failed evaluations ne sont pas persistés. Les conditions MTF réutilisent les observations closes/as-of canoniques.

<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->

### 2026-09-17 — Batch 24B.1 Opportunity ↔ Analytics Linking

**ACCEPTED (candidate pending local validation)** — La jointure Decision ↔ Analytics
devient
une dérivation post-hoc dans `app.evaluation.analytics_attribution`. Le run Analytics
est
sélectionné explicitement ; aucun `latest run` implicite n'est autorisé. La policy
v1 exige une
égalité exacte de provenance et interdit tout nearest-neighbor temporel. Les statuts
distinguent
notamment snapshot manquant, ambiguïté, mismatch dataset/symbole/timeframe/policy/
cursor et
provenance source incomplète. `CandidateOpportunity`, `AnalyticsSnapshot`, le replay
métier et
le business fingerprint restent inchangés.

<!-- BATCH24FR_AGENT_DIALOGUE -->

### ADR-038 — Dialogue IA en français, contrats machine inchangés

**Date :** 2026-09-17
**Statut :** ACCEPTED
**Décision :** les sorties explicatives des agents sont rédigées en français (`fr-FR`) via un contrat transversal du AI Gateway. Les clés JSON, enums, identifiants, références d'évidence et autres tokens machine restent inchangés. Le changement est versionné par `money-heist.prompt-transport.v3` et `money-heist.agent-dialogue.fr.v1`.

**Raisons :** améliorer l'observabilité et la compréhension humaine des échanges de la crew sans fragiliser les schémas structurés, les validateurs, les replays historiques ni les contrats inter-services.

**Conséquences :** légère hausse possible des tokens ; comptabilisation inchangée via `AIUsageRecord`; séparation reproductible des campagnes avant/après grâce à `prompt_render_version`.

<!-- BATCH24FR2_NATIVE_PROMPTS -->

### ADR-039 — French Native Agent Prompts

Décision : maintenir les prompts actifs en français sans traduire rétroactivement les versions
historiques. La reproductibilité repose sur les nouvelles `prompt_version` et sur
`prompt_render_version=money-heist.prompt-transport.v4`. Les contrats machine restent inchangés.

<!-- BATCH_24B2_DECISION_INTELLIGENCE_RECORD -->
### ADR-040 — Decision Intelligence Record read-only

**Date :** 2026-09-17
**Statut :** ACCEPTED (candidate pending local validation)

**Décision :** `DecisionIntelligenceRecord` est un artefact post-hoc sous
`app.evaluation.decision_intelligence`. Il projette les artefacts canoniques du replay et consomme
le `OpportunityAnalyticsLink` 24B.1 sans rematching. Un lien Analytics non résolu n'efface pas la
décision. Le record n'embarque aucun Forward Outcome et n'a aucune autorité sur Scanner, agents,
Risk, PAPER ou LIVE.

**Conséquences :** l'ordre réel des spécialistes est conservé, les failures restent techniques,
les étapes non atteintes ne reçoivent aucun statut métier fabriqué et l'identité du BacktestRun
ainsi que son fingerprint business restent indépendants du record. Le contrat français
`money-heist.agent-dialogue.fr.v1` / `money-heist.prompt-transport.v4` est inchangé.

<!-- BATCH_24B3_SCANNER_ANALYTICS_ATTRIBUTION -->
### ADR-041 — Scanner Analytics Attribution read-only et exact

**Date :** 2026-09-17
**Statut :** ACCEPTED (candidate pending local validation)

**Décision :** `FeatureSnapshot.snapshot_id` est l'identité canonique d'une ScannerEvaluation.
Les trois classes Scanner de 23A.4 sont déplacées vers une primitive neutre partagée. 24B.1 et
24B.3 utilisent le même `AnalyticsSnapshotResolver` et la même policy
`opportunity-analytics-exact-v1`. Aucun fallback précédent/futur n'est autorisé.

**Conséquences :** chaque ScannerEvaluation possède un record d'attribution même sans candidate ;
les candidates peuvent référencer 24B.1/24B.2 ; la provenance MTF/cursor reste causale ; aucune
autorité Analytics ne remonte vers Scanner, Agents, Risk, PAPER ou LIVE ; l'identité du
BacktestRun et le fingerprint business restent inchangés.

<!-- BATCH_24B4_FUNNEL_STAGE_ANALYTICS_ATTRIBUTION -->
### ADR-042 — Funnel Stage Analytics Attribution réutilise le market as-of de la décision

**Date :** 2026-09-17
**Statut :** ACCEPTED

**Décision :** 24B.4 projette le funnel depuis `DecisionIntelligenceRecord` et réutilise
exclusivement la référence Analytics déjà résolue par 24B.1/24B.2. Les stages fixes sont
matérialisés `reached`/`not reached`; les Specialists existent uniquement pour les instances
réellement tentées et gardent `agent_id` comme identité. `TradeProposal` est un stage analytique
distinct et PAPER reste un stage unique contenant les artefacts d'exécution immédiats.

Le `market_as_of` de chaque stage est `DecisionIntelligenceRecord.observed_at`. Les timestamps
opérationnels ultérieurs sont descriptifs et ne peuvent pas déclencher de rematching Analytics.
Une failure technique reste distincte d'une décision métier. Aucun Forward Outcome, score de
qualité ou autorité trading n'entre dans 24B.4.

**Conséquences :** IDs/fingerprints/ordre sont déterministes ; un changement matériel d'un stage
ne doit pas contaminer le fingerprint des autres stages ; les liens Analytics unmatched sont
propagés sans fallback ; les frontières Scanner/Agents/Risk/PAPER/LIVE/Analytics Core restent
inchangées. La validation locale complète du 2026-09-17 autorise la clôture de Batch 24B.

<!-- BATCH_24C2_CHANGELOG -->
### ADR-043 — Projection Decision Intelligence Frontend read-only

**Date :** 2026-09-17
**Statut :** ACCEPTED

**Décision :**
24C.1 expose au Frontend V2 uniquement des projections persistées d'artefacts 24A/24B déjà
calculés. Les endpoints sont `GET` et n'exécutent ni Historical Replay, ni Scanner, ni agents,
ni Risk Engine, ni PAPER/LIVE.

Les runs historiques dépourvus de bundle pré-calculé restent consultables et signalent
explicitement l'indisponibilité Analytics/Decision Intelligence.

**Conséquences :**
la projection frontend n'est pas une nouvelle source de vérité ; aucune identité
`BacktestRun`, aucun business fingerprint et aucune autorité de trading ne sont modifiés.

### ADR-044 — Trading Chart Analytics Overlays causaux et sans recomputation

**Date :** 2026-09-18
**Statut :** ACCEPTED

**Décision :**
24C.2 projette vers le chart les événements, structures, pivots et patterns déjà produits par
Analytics ainsi que les artefacts Scanner/Funnel déjà attribués. Le navigateur peut filtrer,
masquer et sélectionner ces objets mais ne peut pas les recalculer.

La géométrie et la connaissance sont séparées : un événement reste placé à `event_at` mais n'est
visible qu'à `available_at`; un pivot ZigZag reste placé à `pivot_at` mais n'est visible qu'à
`confirmed_at`; un pattern n'affiche que le lifecycle connu au curseur ; un funnel conserve
`market_as_of` avec `operational_at` comme temps de connaissance lorsqu'il existe.

**Conséquences :**
les toggles Zustand sont de l'état UI uniquement ; les anciens runs dégradent proprement ;
l'absence de géométrie persistée n'entraîne aucun recalcul ; Scanner, agents, Risk, PAPER, LIVE,
Forward Outcomes, `BacktestRun.run_id` et business fingerprints restent inchangés.

## Changelog documentation — 2026-09-18 — Clôture Batch 24C.2

- 24C.1 Backend Projection API intégré à la documentation canonique ;
- 24C.2 Trading Chart Analytics Overlays livré et validé ;
- causalité `available_at` / `confirmed_at` / `operational_at` préservée dans le replay visuel ;
- toggles, filtres et sélection préparés pour 24C.3 ;
- aucune recomputation métier ou autorité LIVE ajoutée ;
- prochaine étape : Batch 24C.3 — Decision Intelligence Inspector.

<!-- BATCH_24C3_CHANGELOG -->
### ADR-045 — Materialization post-run obligatoire avant lecture frontend

**Date :** 2026-09-18
**Statut :** ACCEPTED

**Décision :** les artefacts Analytics/Decision Intelligence nécessaires au Frontend V2 sont calculés au terme du replay normal, ajoutés aux exports de campagne puis persistés par le watcher terminal existant. Les endpoints GET ne calculent rien à la demande.

Le post-traitement est observation-only : il ne rejoue ni Scanner, ni agents, ni Risk Engine, ni PAPER/LIVE.

### ADR-046 — Inspector Decision Intelligence unique et contextuel

**Date :** 2026-09-18
**Statut :** ACCEPTED

**Décision :** 24C.3 réutilise le panneau droit existant, `selectedOpportunityId`, `selectedAnalyticsObject` et `inspectorOpen`. Un clic sur un objet chart ouvre l'Inspector et charge le détail 24C.1 seulement lorsqu'un `opportunity_id` existe. Les objets Analytics sans opportunité restent inspectables sans inventer de chaîne de décision.

**Conséquences :** séparation stricte UI / autorité métier, affichage explicite de la causalité, dégradation contrôlée des anciens runs et absence totale d'impact LIVE.

<!-- ADR047_PROJECT_MEMORY_CONTEXT -->
### ADR-047 — Mémoire projet déterministe et contrat de reprise de contexte

**Date :** 2026-09-19  
**Statut :** ACCEPTED

**Décision :** GitHub `main` reste la vérité intégrée. `00_ETAT_ACTUEL_POST_BATCH_15.md` devient la mémoire courte de démarrage : HEAD audité, architecture actuelle, état des lots, invariants, bloqueurs et handoff. `09_ROADMAP_DEVELOPPEMENT.md` conserve le futur ; `10_DECISIONS_ET_CHANGELOG.md` conserve le pourquoi ; les documents de domaine conservent les détails.

Une nouvelle conversation ne doit pas reconstruire l'état du projet uniquement depuis l'historique conversationnel.

**Raison :** le projet a dépassé la capacité pratique d'un contexte conversationnel monolithique et les anciens addenda documentaires peuvent rester historiquement vrais tout en étant obsolètes pour l'état courant.

**Conséquences :**
- le fichier `00` doit rester compact et être remplacé/rafraîchi, pas seulement allongé ;
- le HEAD doit être vérifié au démarrage d'une nouvelle session ;
- un écart de HEAD impose l'inspection des commits depuis la baseline mémorisée ;
- les modifications locales non commités doivent être signalées explicitement dans le handoff ;
- les conversations restent informatives mais ne remplacent pas Git et les ADR.

<!-- BATCH24D4_CHANGELOG_CLOSURE -->
## Changelog documentation — 2026-09-19 — Synchronisation post-24D.4

- 24D.4 Research Reports & Evidence Explorer intégré sur `a03ade86` ;
- pipeline post-run 24A → 24B → 24C → 24D.1/2/3/4 consolidé ;
- sidecars Decision Quality et Evidence Index persistés ;
- endpoints Research GET read-only et Research Explorer frontend livrés ;
- gate d'hygiène statique fermée (`f9061e06`) ;
- format des prompts normalisé (`faf713c4`) ;
- timing causal des transitions de patterns corrigé (`c28b71d5`) ;
- aucune autorité Scanner/Agents/Risk/PAPER/LIVE déplacée ;
- mémoire projet courte formalisée par ADR-047.

<!-- DOC_ACTIVE_REALIGN_20260919 -->
## Changelog documentation — 2026-09-19 — Réalignement des documents actifs

- `00` référence désormais explicitement la baseline intégrée auditée `cb0c26a0` et distingue cette baseline du HEAD futur ;
- `01`, `02`, `08`, `09` et `12` sont réalignés sur l'état post-24D.4 ;
- le transport Prompt Cache actif est documenté en `money-heist.prompt-transport.v4` ;
- les snapshots intermédiaires `CURRENT / NEXT / PLANNED` de 24C/24D sont retirés de la roadmap active ;
- `04` et `07` passent du statut historique « spécification initiale » à « référence active » ;
- les documents de batch restent disponibles sous `docs/archives/` mais ne sont pas une source d'état courant ;
- aucune autorité Scanner, Agents, Risk, PAPER ou LIVE n'est modifiée par ce réalignement.

### ADR-048 — Positionnement marché explicite et Spot long-only

**Date :** 2026-09-19
**Statut :** ACCEPTED

**Décision :**
Toute campagne historique destinée à représenter le premier marché Spot déclare explicitement `SPOT_LONG_ONLY`. Le mode générique `LONG_SHORT` reste disponible uniquement pour les marchés/runtimes qui autorisent réellement l’ouverture d’une exposition nette short.

Pour `SPOT_LONG_ONLY` :
- Professor FINAL reçoit `allowed_trade_directions=[LONG]` et doit produire `LONG` ou `NO_TRADE` ;
- une direction interdite n’est jamais convertie automatiquement en LONG ;
- le Risk Engine rejette défensivement toute proposition SHORT avec `SHORT_NOT_SUPPORTED` ;
- le PaperBroker est configuré `allow_short=False`, ce qui interdit l’ouverture nette SHORT tout en autorisant une vente qui réduit/clôture un LONG existant ;
- la capability entre dans les hypothèses matérielles de `BacktestConfig` et modifie le `run_id`.

**Raison :**
Aligner les preuves historiques avec ADR-020 et le premier LIVE Kraken Spot, qui refuse déjà les entrées SHORT. Une campagne autorisant des shorts mesure une stratégie inexécutable telle quelle sur cette cible.

**Conséquence :**
La première campagne 1 mois exécutée avant ADR-048 reste un smoke technique valide de la chaîne, mais ne constitue pas une baseline économique Spot. Elle doit être rejouée en `SPOT_LONG_ONLY` avant les campagnes empiriques 3/6/9/12 mois.

### ADR-049 — Résumé opérateur et analyse avancée séparés

**Date :** 2026-09-19
**Statut :** ACCEPTED

**Décision :**
La page de résultat d'une campagne Backtest sépare deux niveaux de lecture construits à partir des mêmes artefacts canoniques :

- `Résumé` est la vue par défaut et expose l'identité du run, les métriques homogènes DESIGN / VALIDATION / OOS, le Decision Funnel compact et l'equity OOS déjà persistée ;
- `Analyse avancée` conserve les diagnostics techniques, la configuration détaillée, le Historical Replay, Analytics overlays, Decision Intelligence, Research Explorer, trades et events ;
- les requêtes lourdes Replay / Analytics / Research ne sont activées qu'à l'ouverture de l'Analyse avancée ;
- aucune logique Scanner, Professor, Risk, PAPER ou Research n'est réimplémentée dans le frontend ;
- `PeriodSummary.decision_funnel`, déjà produit par le backend, devient explicitement conservé par le schéma frontend ;
- le rendement net affiché dans le Résumé est un ratio de présentation `trading_net / initial_balance`, pas une nouvelle métrique métier persistée.

**Raison :**
La page post-campagne avait accumulé résultat économique, diagnostics d'exécution, replay causal, Decision Intelligence et recherche 24D au même niveau visuel. Cette densité rendait difficile la réponse à la question opérateur initiale : « qu'a produit la campagne et où faut-il investiguer ? ».

**Conséquences :**
- la lecture courante devient plus rapide sans supprimer les outils avancés ;
- les trois périodes restent séparées et comparables avec les mêmes métriques ;
- OOS reste explicitement identifié comme OUT-OF-SAMPLE ;
- les artefacts Research restent observationnels ;
- aucune autorité de tuning ou LIVE n'est ajoutée au frontend.

### ADR-050 — Offload des calculs post-run pour préserver la réactivité FastAPI

**Date :** 2026-09-19
**Statut :** ACCEPTED

**Décision :**
Les calculs CPU post-replay d'une campagne Backtest ne doivent pas s'exécuter directement sur l'event loop FastAPI. Le parsing du dataset dans le job, les mesures 23A/Forward Outcomes, la sérialisation des exports, le catalogue Denver et la finalisation 24A → 24D sont déportés via `asyncio.to_thread`.

**Raison :**
Une campagne longue pouvait entrer en finalisation synchrone pendant plusieurs minutes. Pendant ce temps, même des routes read-only triviales telles que `/api/frontend/v2/capabilities` et `/progress` ne recevaient aucun header et le proxy Next.js finissait par lever `UND_ERR_HEADERS_TIMEOUT`.

**Conséquences :**
- le serveur reste réactif pendant PREPARING, mesure post-hoc et FINALIZING ;
- le polling frontend et l'annulation coopérative redeviennent utilisables ;
- les fonctions de calcul, artefacts, règles de trading et fingerprints métier restent inchangés ;
- aucune autorité Scanner, Professor, Risk, PAPER ou LIVE n'est déplacée ;
- augmenter artificiellement le timeout du proxy n'est pas la solution retenue.
