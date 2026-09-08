# Money Heist — Spécification Maître du Projet

**Document :** Spécification Maître du Projet  
**Statut :** Document vivant  
**Version :** 0.2  
**Objectif :** Source de vérité pour la conception, le développement, les tests et l’évolution de l’application Money Heist.

---

## 1. Vision

**Money Heist** est une plateforme de trading crypto assistée par IA, construite autour d’une architecture multi-agents contrôlée.

Le système est conçu comme une équipe d’agents IA spécialisés, dirigée par un orchestrateur nommé **The Professor**. Les agents analysent les marchés de manière indépendante, confrontent leurs conclusions, estiment la valeur d’une analyse supplémentaire et proposent des décisions de trading.

Le système doit pouvoir évoluer avec le temps grâce à :
- la mesure des performances ;
- la réputation des agents ;
- le shadow testing ;
- le recrutement contrôlé de nouveaux agents spécialisés ;
- l’allocation dynamique du budget IA ;
- plusieurs systèmes de trading avec différents profils de risque.

L’objectif long terme est de déterminer si le système peut générer un avantage de trading durable et, à terme, produire suffisamment de valeur nette pour couvrir ses propres coûts d’IA.

Cet objectif ne doit **jamais** passer avant :
- la protection du capital ;
- les limites de risque ;
- les mécanismes d’arrêt ;
- l’autorité humaine.

---

## 2. Principes fondamentaux

### 2.1 L’IA propose ; les systèmes déterministes autorisent

Les agents IA peuvent :
- analyser ;
- raisonner ;
- comparer des hypothèses ;
- recommander des trades ;
- proposer des paramètres de position ;
- recommander quels experts consulter ;
- recommander des changements dans l’utilisation des agents.

Les agents IA ne peuvent **jamais** contourner les règles de sécurité déterministes.

```text
Données de marché
    ↓
Analyse
    ↓
Proposition IA
    ↓
Risk Engine déterministe
    ↓
Moteur d’exécution
```

### 2.2 Les règles de risque sont constitutionnelles

Les éléments suivants ne peuvent pas être modifiés de manière autonome par la crew :
- risque maximal par trade ;
- perte journalière maximale ;
- exposition maximale du portefeuille ;
- levier maximal ;
- règles de drawdown maximal ;
- plafond dur des dépenses IA ;
- permissions et identifiants API ;
- kill switch humain ;
- restrictions de retrait ;
- règles de promotion des agents.

Les agents peuvent proposer des changements, mais toute modification exige une autorisation externe.

### 2.3 Aucun agent ne reçoit un accès libre à l’exchange

Les agents ne reçoivent jamais directement les secrets ou clés privées de l’exchange.

Le système ne doit pas leur fournir une fonction générique du type :

```text
execute_arbitrary_exchange_request()
```

À la place, l’application expose des opérations contrôlées telles que :

```text
propose_trade()
cancel_allowed_order()
request_market_snapshot()
```

Les opérations réelles sur l’exchange sont exécutées par des services backend déterministes après validation.

Les permissions de retrait doivent rester désactivées pour les clés API de trading.

### 2.4 Aucun trade forcé

`NO_TRADE` est une décision de premier niveau.

Le système doit préférer l’absence de position lorsque :
- les preuves sont contradictoires ;
- l’avantage attendu est insuffisant ;
- les frais rendent l’opportunité non rentable ;
- la volatilité dépasse les limites autorisées ;
- le coût de l’analyse IA n’est pas justifié ;
- l’exposition globale est déjà trop élevée ;
- les règles de risque empêchent l’exécution.

### 2.5 L’apprentissage repose sur des preuves

La crew ne doit pas “apprendre” à partir de souvenirs vagues de gains ou de pertes.

L’apprentissage doit s’appuyer principalement sur des données structurées :
- régime de marché ;
- variables d’entrée ;
- agents consultés ;
- conclusions des agents ;
- proposition de trade ;
- décision du Risk Engine ;
- détails d’exécution ;
- frais ;
- slippage ;
- résultat ;
- MAE ;
- MFE ;
- coût IA ;
- métriques d’attribution.

Toute adaptation doit être :
- mesurable ;
- testable ;
- réversible.

---

## 3. Budget initial du prototype

### 3.1 Capital de trading

Capital réel initial :

**100 €**

Ce capital est volontairement faible. Son objectif est de valider le comportement réel de l’exécution, et non de maximiser immédiatement le rendement monétaire.

### 3.2 Budget IA

Budget initial de R&D IA :

**Objectif : environ 20 à 30 €**

Ce budget est payé séparément du capital de trading pendant la phase prototype.

Le système doit suivre :
- le coût IA total ;
- le coût par agent ;
- le coût par opportunité ;
- le coût par trade exécuté ;
- le coût par modèle ;
- le coût par stratégie ;
- le coût par régime de marché.

Un plafond logiciel dur doit être prévu.

### 3.3 Objectif économique initial

Pendant la phase prototype, deux PnL sont suivis séparément.

#### PnL Trading

```text
Gains / pertes de trading
- Frais exchange
- Slippage
- Funding / coûts d’exécution
= PnL Trading Net
```

#### PnL Économique

```text
PnL Trading Net
- Coût IA
- Coût infrastructure si pertinent
= PnL Économique Net
```

Le premier prototype n’a pas besoin d’être économiquement autofinancé.

L’objectif initial est de déterminer si le système de trading possède un avantage mesurable et positif.

---

## 4. Objectif long terme : autofinancement de l’IA

Un KPI principal à long terme sera :

```text
Ratio d’autofinancement IA
=
Valeur nette de trading attribuable au système
----------------------------------------------
Coût d’exploitation IA
```

Interprétation :

```text
< 1,0x  → l’IA n’est pas autofinancée
= 1,0x  → seuil de rentabilité
> 1,0x  → l’IA est autofinancée
```

Le système ne doit **jamais** augmenter le risque dans le seul but d’améliorer ce ratio.

Les méthodes autorisées pour améliorer l’efficacité économique incluent :
- réduire les appels IA inutiles ;
- utiliser des modèles moins coûteux lorsque c’est pertinent ;
- améliorer les filtres déterministes ;
- appeler moins de spécialistes sur les opportunités faibles ;
- améliorer les prompts ;
- supprimer les analyses redondantes ;
- relever le seuil de qualité avant une analyse coûteuse ;
- augmenter le capital uniquement lorsque les preuves le justifient.

---

## 5. Architecture des agents Money Heist

### 5.1 The Professor

**Rôle :** Orchestrateur et décideur IA final.

Responsabilités :
- examiner le contexte de marché ;
- décider si une analyse approfondie est justifiée ;
- sélectionner les spécialistes pertinents ;
- agréger les conclusions indépendantes ;
- évaluer les désaccords ;
- demander une analyse supplémentaire si nécessaire ;
- produire une proposition structurée :
  - LONG ;
  - SHORT ;
  - NO_TRADE ;
- estimer son niveau de confiance ;
- définir la thèse et les conditions d’invalidation ;
- estimer si une dépense IA supplémentaire est justifiée.

The Professor ne peut jamais contourner le Risk Engine.

### 5.2 Berlin

**Rôle :** Spécialiste du régime de marché et de la tendance.

Domaines principaux :
- structure de tendance ;
- relations EMA ;
- ADX ;
- régime de volatilité ;
- contexte multi-timeframes ;
- continuation ou épuisement de tendance.

### 5.3 Tokyo

**Rôle :** Spécialiste momentum.

Domaines principaux :
- momentum ;
- accélération ;
- qualité des breakouts ;
- RSI ;
- MACD ;
- expansion du volume ;
- continuation court terme.

### 5.4 Nairobi

**Rôle :** Spécialiste price action, structure de marché et liquidité.

Domaines principaux :
- supports et résistances ;
- structure de marché ;
- swing highs / swing lows ;
- breakouts et retests ;
- zones de liquidité ;
- faux breakouts ;
- contexte price action.

### 5.5 Rio

**Rôle :** Spécialiste dérivés et sentiment.

Domaines principaux :
- funding ;
- open interest ;
- liquidations ;
- positionnement futures ;
- données de sentiment lorsque disponibles.

### 5.6 Denver

**Rôle :** Spécialiste quantitatif et statistique.

Domaines principaux :
- performances historiques des setups ;
- probabilités conditionnelles ;
- distributions ;
- espérance de gain ;
- statistiques par régime ;
- résultats de backtest ;
- robustesse des signaux.

### 5.7 Palermo

**Rôle :** Red Team / Devil’s Advocate.

Palermo est obligatoire pour les décisions suffisamment importantes.

Responsabilités :
- argumenter contre la thèse dominante ;
- détecter le biais de confirmation ;
- identifier les invalidations ;
- détecter les risques de faux breakout ;
- identifier les pièges de liquidité ;
- remettre en question la qualité des données ;
- détecter les risques de corrélation cachés ;
- chercher activement des raisons de refuser le trade.

Palermo n’est pas évalué uniquement selon son impact direct sur le PnL. La réduction du drawdown et des risques extrêmes fait partie de ses métriques essentielles.

### 5.8 Lisbon

**Rôle :** CFO / économie IA / efficacité organisationnelle.

Responsabilités :
- suivre les dépenses IA ;
- calculer le coût par décision ;
- calculer le coût par agent ;
- estimer la valeur produite par agent ;
- suivre le ratio d’autofinancement ;
- détecter les dépenses inutiles ;
- recommander les états ACTIVE / ON_DEMAND / SHADOW / PROBATION ;
- estimer si une analyse IA supplémentaire est économiquement justifiée ;
- participer à l’évaluation des recrutements.

Lisbon ne contrôle pas les limites de risque de trading.

### 5.9 Risk Engine

**Type :** Service déterministe, non discrétionnaire.

Responsabilités :
- calcul de la taille des positions ;
- risque maximal par trade ;
- perte journalière maximale ;
- risque portefeuille maximal ;
- exposition corrélée maximale ;
- restrictions de levier ;
- limites de drawdown ;
- contraintes de taille minimale des ordres ;
- exigences de stop ;
- kill switches ;
- rejet des propositions invalides.

Sa décision fait autorité.

---

## 6. États des agents

Les agents spécialisés peuvent avoir les états suivants :

- **ACTIVE** — utilisé régulièrement lorsqu’il est pertinent.
- **ON_DEMAND** — disponible mais appelé seulement lorsque son expertise est utile.
- **SHADOW** — produit des analyses sans influencer le trading réel.
- **PROBATION** — en période d’évaluation avec influence limitée et logs renforcés.
- **DISABLED** — temporairement désactivé.

`DISABLED` ne signifie pas suppression définitive.

---

## 7. Agents Core et spécialistes

### Fonctions Core

Les fonctions suivantes doivent toujours exister :
- orchestration ;
- revue contradictoire ;
- contrôle de risque déterministe ;
- contrôle des coûts ;
- audit et journalisation.

Les implémentations peuvent évoluer, mais ces fonctions ne peuvent pas être supprimées automatiquement.

### Fonctions spécialistes

Les spécialistes peuvent :
- passer en ON_DEMAND ;
- passer en SHADOW ;
- redevenir ACTIVE ;
- être remplacés par de meilleurs spécialistes ;
- être divisés en rôles plus spécialisés.

---

## 8. Recrutement contrôlé de nouveaux agents

Money Heist pourra proposer et créer de nouveaux agents spécialisés.

Processus cible :

```text
Faiblesse observée
      ↓
Hypothèse de recrutement
      ↓
Spécification du candidat
      ↓
Validation sécurité
      ↓
Agent SHADOW
      ↓
Backtest / replay / paper trading
      ↓
Probation
      ↓
ACTIVE / ON_DEMAND / REJETÉ
```

Chaque proposition de recrutement doit préciser :
- rôle ;
- problème traité ;
- valeur attendue ;
- données nécessaires ;
- outils nécessaires ;
- classe de modèle IA ;
- coût de calcul estimé ;
- métrique de succès ;
- durée d’évaluation.

Un nouvel agent :
- commence sans autorité de trading ;
- ne peut pas accéder aux secrets ;
- ne peut pas modifier le Risk Engine ;
- ne peut pas s’accorder de permissions ;
- ne peut pas créer librement du code de production ;
- ne peut pas supprimer les composants de sécurité Core.

L’application doit supporter :
- un nombre maximal de spécialistes actifs ;
- un nombre maximal de candidats SHADOW ;
- une fréquence maximale de recrutement ;
- un budget IA par candidat ;
- une promotion réversible.

---

## 9. Agents temporaires / Task Force

The Professor pourra demander des spécialistes temporaires pour certaines situations exceptionnelles.

Exemples :
- spécialiste événement Ethereum ;
- spécialiste événement macro ;
- spécialiste panne exchange ;
- spécialiste cascade de liquidations.

Ces agents temporaires :
- disposent d’outils limités ;
- disposent d’un budget limité ;
- expirent automatiquement ;
- n’ont aucune autorité de trading au départ ;
- sont intégralement journalisés.

---

## 10. Raisonnement indépendant

Afin de réduire le groupthink, les analyses initiales des spécialistes doivent être généralement indépendantes.

Un spécialiste reçoit :
- un snapshot de marché ;
- sa mission ;
- les outils pertinents.

Il ne doit généralement **pas** recevoir l’avis des autres spécialistes avant de produire sa première conclusion.

The Professor reçoit ensuite les analyses indépendantes et les agrège.

Palermo peut alors recevoir le consensus afin de l’attaquer directement.

---

## 11. Sorties structurées des agents

Les décisions des agents doivent utiliser des schémas structurés plutôt que du texte libre lorsque cela est possible.

Exemple conceptuel :

```json
{
  "symbol": "BTCUSDT",
  "direction": "LONG",
  "confidence": 0.73,
  "market_regime": "bullish_trend",
  "thesis": [],
  "counter_evidence": [],
  "invalidation": [],
  "recommended_entry": null,
  "recommended_stop": null,
  "recommended_targets": [],
  "expected_rr": null,
  "request_more_analysis": false
}
```

Les schémas définitifs seront précisés dans la documentation fonctionnelle.

---

## 12. Niveaux de consommation IA

Le système doit supporter plusieurs niveaux d’utilisation de l’IA.

### Niveau 0 — Déterministe uniquement
Exemples :
- données de marché ;
- calculs d’indicateurs ;
- détection d’événements ;
- scanner.

Coût IA : quasi nul.

### Niveau 1 — Sentinel
Une IA peu coûteuse vérifie si l’événement mérite une analyse plus poussée.

### Niveau 2 — Mini Crew
The Professor + un nombre limité de spécialistes pertinents.

### Niveau 3 — Full Crew
Analyse complète pour les opportunités rares à forte valeur potentielle.

La majorité des observations de marché doivent rester au Niveau 0.

---

## 13. Gestion du budget IA

Avant une analyse coûteuse, le système doit estimer :
- le coût IA attendu ;
- le budget quotidien / mensuel restant ;
- la qualité de l’opportunité ;
- la valeur probable de l’information supplémentaire.

Les opportunités faibles ne doivent pas consommer d’analyse IA coûteuse.

Les contrôles de budget doivent inclure :
- un objectif journalier souple ;
- un plafond total dur ;
- le coût par agent ;
- le coût par opportunité ;
- un fallback vers des modèles moins coûteux.

---

## 14. Systèmes de trading et profils de risque

L’architecture doit pouvoir supporter plusieurs systèmes de trading indépendants.

### Conservative / Vault
- faible fréquence de trading ;
- confirmations strictes ;
- faible risque ;
- biais vers les timeframes élevés ;
- levier faible ou nul.

### Balanced
- fréquence moyenne ;
- risque modéré ;
- plusieurs approches ;
- candidat principal pour le premier système LIVE.

### Aggressive / Tokyo
- fréquence d’opportunités plus élevée ;
- tolérance plus forte à la volatilité ;
- surveillance plus serrée ;
- risque supérieur mais plafonné.

Les paramètres de risque doivent être définis dans la configuration, et non uniquement dans les prompts.

---

## 15. Systèmes LIVE et SHADOW

L’architecture initiale doit supporter :

```text
Un système LIVE
+
Plusieurs systèmes SHADOW
```

Les systèmes SHADOW :
- reçoivent les données de marché réelles ;
- prennent des décisions virtuelles complètes ;
- simulent l’exécution ;
- enregistrent un PnL virtuel ;
- intègrent des frais et du slippage estimés ;
- ne peuvent pas envoyer d’ordres réels.

Cela permet de comparer les stratégies et profils de risque sans diviser les 100 € initiaux.

---

## 16. Couche portefeuille maître — Futur

Une version future pourra ajouter :

### Master Professor / Allocator
Responsabilités :
- comparer les systèmes ;
- analyser les performances selon les régimes ;
- recommander l’allocation du capital.

### Master Risk Engine
Responsabilités :
- détecter les expositions corrélées entre systèmes ;
- plafonner l’exposition globale au risque crypto ;
- gérer les risques simultanés ;
- empêcher plusieurs systèmes de prendre sans le savoir le même risque macro.

Cette couche n’est pas nécessaire pour le premier prototype.

---

## 17. Couche de données de marché

La couche market data devra progressivement supporter :
- OHLCV ;
- trades ;
- snapshots d’order book lorsque pertinent ;
- funding ;
- open interest ;
- liquidations lorsque disponibles ;
- métadonnées des symboles ;
- contraintes de l’exchange.

Les indicateurs et calculs statistiques doivent être réalisés par du code déterministe plutôt que par le LLM lorsque cela est possible.

---

## 18. Univers de trading initial

Le prototype doit commencer avec un univers volontairement réduit.

Candidats initiaux proposés :

```text
BTC
ETH
SOL
```

L’exchange et les paires exactes seront choisis avant l’intégration réelle.

L’univers sera élargi uniquement après stabilisation.

---

## 19. Couche d’exécution

Le moteur d’exécution devra prendre en compte :
- ordres market et limit ;
- taille minimale d’ordre ;
- tick size ;
- précision des quantités ;
- fills partiels ;
- ordres rejetés ;
- erreurs réseau ;
- signaux obsolètes ;
- protection contre les doubles exécutions ;
- slippage ;
- frais ;
- placement des stops ;
- réconciliation des ordres.

Le paper trading devra se rapprocher autant que raisonnablement possible du comportement réel.

---

## 20. Sécurité

Principes obligatoires :
- identifiants stockés hors du code source ;
- fichiers `.env` jamais commités ;
- permission de retrait désactivée ;
- permissions exchange minimales ;
- secrets jamais inclus dans les prompts IA ;
- validation de tous les appels d’outils ;
- contrôles de permissions déterministes ;
- kill switch d’urgence ;
- journal d’audit complet.

---

## 21. Données et journalisation

Chaque décision importante doit pouvoir être reconstruite.

Données minimales :

### Contexte marché
- timestamp ;
- symbole ;
- timeframe ;
- variables de marché ;
- régime de marché.

### Contexte IA
- agent ;
- modèle ;
- version du prompt ;
- ID du snapshot d’entrée ;
- sortie structurée ;
- consommation de tokens ;
- coût ;
- latence.

### Contexte décisionnel
- spécialistes sélectionnés ;
- conclusion du Professor ;
- objections de Palermo ;
- décision du Risk Engine ;
- raison éventuelle du rejet.

### Exécution
- ordre proposé ;
- ordre soumis ;
- fills ;
- frais ;
- slippage ;
- stop ;
- objectifs.

### Résultat
- PnL réalisé ;
- MAE ;
- MFE ;
- durée de détention ;
- raison de sortie.

---

## 22. Métriques de performance

### Trading
- PnL net ;
- rendement ;
- win rate ;
- profit factor ;
- expectancy ;
- R/R moyen ;
- drawdown maximal ;
- Sharpe ;
- Sortino ;
- exposition ;
- fréquence de trading.

### IA
- coût par agent ;
- coût par opportunité ;
- coût par trade ;
- coût par trade rentable ;
- coût par modèle ;
- coût par stratégie ;
- ratio d’autofinancement.

### Qualité des agents
- précision directionnelle ;
- calibration ;
- utilité des veto ;
- contribution marginale ;
- performance par régime ;
- performance par actif ;
- performance par timeframe.

---

## 23. Attribution de performance des agents

La qualité d’un agent ne doit pas être évaluée uniquement selon son win rate.

Méthodes possibles :
- tests d’ablation ;
- comparaison SHADOW ;
- analyse contrefactuelle ;
- suivi des changements de décision ;
- estimation des pertes évitées ;
- estimation du PnL incrémental ;
- contribution au drawdown.

Les résultats doivent influencer la fréquence d’utilisation des agents plutôt qu’entraîner automatiquement leur suppression définitive.

---

## 24. Backtesting et validation

Avant toute montée en capital significative, les stratégies doivent passer par :

```text
Replay historique
    ↓
Backtest
    ↓
Validation hors échantillon
    ↓
Walk-forward
    ↓
Shadow / paper trading
    ↓
Petit capital réel
```

Les tests doivent tenir compte de :
- look-ahead bias ;
- overfitting ;
- fills irréalistes ;
- frais ;
- slippage ;
- dépendance au régime de marché.

---

## 25. Gestion des pannes

Le système doit gérer proprement :
- timeout IA ;
- sortie IA invalide ;
- timeout exchange ;
- données manquantes ;
- données obsolètes ;
- panne partielle de marché ;
- panne base de données ;
- état d’ordre incohérent ;
- indisponibilité de l’API modèle ;
- exceptions inattendues.

Comportement par défaut en cas d’incertitude sur l’autorisation d’un trade :

**Ne pas ouvrir de nouvelle position.**

---

## 26. Direction technique initiale

Stack provisoire :

### Backend
- Python
- FastAPI

### Données / logique de trading
- écosystème Python ;
- couche déterministe pour indicateurs et statistiques.

### Base de données
- PostgreSQL ou base locale légère pour la toute première version.

### Frontend
- dashboard web ; technologie à confirmer lorsque le développement frontend commencera.

### IA
- API OpenAI ;
- sélection des modèles configurable.

### Configuration
- variables d’environnement pour les secrets ;
- configuration non sensible versionnée ;
- profils de risque configurables.

Les choix techniques restent révisables jusqu’à leur milestone d’implémentation.

---

## 27. Structure de dépôt proposée

```text
money-heist/
│
├── app/
│   ├── agents/
│   ├── intelligence/
│   ├── market/
│   ├── trading/
│   ├── evaluation/
│   ├── storage/
│   ├── api/
│   └── config/
│
├── tests/
├── docs/
├── scripts/
├── .env.example
├── pyproject.toml
└── README.md
```

---

## 28. Philosophie de développement

Le développement doit se faire par petits lots testables.

Chaque lot doit :
1. avoir un objectif précis ;
2. éviter les refactorings sans rapport ;
3. inclure des tests lorsque pertinent ;
4. rester exécutable ;
5. documenter les migrations / étapes d’installation ;
6. identifier les fichiers modifiés ;
7. mettre à jour la documentation pertinente.

Aucune grande fonctionnalité ne doit être livrée sous forme de réécriture opaque si elle peut être décomposée proprement.

---

## 29. Workflow de livraison

Le projet actif sera maintenu localement dans VS Code.

ChatGPT fournira le développement sous forme de fichiers ZIP.

Convention de nommage :

```text
money-heist_batch_01_foundation.zip
money-heist_batch_02_market-data.zip
money-heist_batch_03_agents.zip
```

Les gros lots pourront être découpés :

```text
money-heist_batch_03a_agents-core.zip
money-heist_batch_03b_agents-specialists.zip
```

Chaque ZIP devra contenir :
- le code ;
- les tests ;
- les exemples de configuration ;
- les instructions de migration / installation si nécessaire ;
- un `CHANGELOG_BATCH.md`.

L’objectif est de pouvoir extraire / copier les fichiers directement dans le projet VS Code avec un minimum de reconstruction manuelle.

Aucun secret ne doit apparaître dans les ZIP.

---

## 30. Contrainte sur le nombre de fichiers source

L’espace de sources du projet disponible pour ChatGPT est limité à environ **25 fichiers**.

La documentation doit donc être volontairement consolidée.

Objectif : **8 à 12 documents permanents maximum**.

Jeu de documents proposé :

```text
01_PROJECT_MASTER.md
02_ARCHITECTURE.md
03_SYSTEME_AGENTS.md
04_TRADING_ET_RISQUE.md
05_MARKET_DATA_ET_EXECUTION.md
06_EVALUATION_ET_APPRENTISSAGE.md
07_SECURITE_ET_OPERATIONS.md
08_API_ET_MODELES_DE_DONNEES.md
09_ROADMAP_DEVELOPPEMENT.md
10_DECISIONS_ET_CHANGELOG.md
```

La documentation des features doit être intégrée autant que possible dans ces documents de domaine, plutôt que de créer un fichier permanent pour chaque petite fonctionnalité.

Cela permet de préserver de la place pour :
- les fichiers d’architecture importants ;
- certains snapshots de code si nécessaire ;
- les schémas ;
- la documentation opérationnelle.

---

## 31. Règles de documentation

### Document maître

`01_PROJECT_MASTER.md` est la source de vérité de haut niveau.

Il répond à :
- qu’est-ce que le projet ;
- pourquoi existe-t-il ;
- quels sont ses principes ;
- quels sont ses composants majeurs ;
- quelles contraintes ne peuvent pas être violées.

### Documents de domaine

Les spécifications détaillées sont regroupées dans les documents thématiques.

Le Master doit éviter de dupliquer tous les détails d’implémentation.

### Journal de décisions

Les décisions importantes doivent être enregistrées avec :
- date ;
- décision ;
- justification ;
- alternatives considérées ;
- conséquences.

---

## 32. Roadmap initiale de développement

### Phase 0 — Spécification
- établir la spécification maître ;
- définir le premier milestone ;
- choisir l’exchange / données ;
- définir le profil de risque initial ;
- définir les hypothèses du paper trading.

### Phase 1 — Fondations
- structure du projet Python ;
- configuration ;
- logging ;
- fondation base de données ;
- framework de tests ;
- endpoint FastAPI de santé.

### Phase 2 — Données de marché
- connecteur market data ;
- snapshots normalisés ;
- indicateurs ;
- scanner ;
- persistance des données.

### Phase 3 — Paper Broker
- compte virtuel ;
- ordres ;
- fills ;
- frais ;
- slippage ;
- PnL ;
- stops et targets.

### Phase 4 — Core Money Heist Crew
Ensemble initial :
- Professor ;
- Berlin ;
- Tokyo ;
- Nairobi ;
- Palermo ;
- Lisbon.

Rio et Denver seront ajoutés lorsque les données et métriques nécessaires seront disponibles.

### Phase 5 — Risk Engine
- position sizing ;
- limites par trade ;
- limites journalières ;
- exposition portefeuille ;
- rejet des trades ;
- kill switch.

### Phase 6 — Pipeline décisionnel complet

```text
Scanner
→ Professor
→ Spécialistes
→ Palermo
→ Professor
→ Risk Engine
→ Paper Broker
→ Évaluation
```

### Phase 7 — Profils SHADOW
- Conservative ;
- Balanced ;
- Aggressive.

Un seul système peut être LIVE au départ.

### Phase 8 — Dashboard
- état du portefeuille ;
- signaux ;
- décisions des agents ;
- dépenses IA ;
- PnL ;
- drawdown ;
- historique des décisions.

### Phase 9 — Petit trading LIVE
Utilisation des 100 € uniquement après validation du paper trading et des contrôles de sécurité.

### Phase 10 — Organisation adaptative
- réputation ;
- états des agents ;
- tests d’ablation ;
- recrutement contrôlé ;
- agents temporaires ;
- optimisation du compute.

---

## 33. Premier profil LIVE — Provisoire

Le premier profil LIVE devrait être **Balanced**, mais les valeurs exactes seront définies avant le trading réel.

Orientation actuelle :

```text
Capital : 100 €

Risque par trade :
petit pourcentage fixe de l’equity

Risque simultané portefeuille :
strictement plafonné

Perte journalière :
strictement plafonnée

Levier :
nul ou minimal au départ

Nouvelles positions :
bloquées après déclenchement des seuils de sécurité
```

Les valeurs numériques exactes ne sont pas encore figées volontairement.

---

## 34. Autorité humaine

L’utilisateur reste l’autorité finale.

Le système doit toujours permettre :
- d’arrêter le trading ;
- de désactiver des agents ;
- de désactiver les appels IA ;
- d’arrêter les analyses automatisées ;
- de passer un système LIVE en SHADOW ;
- de révoquer l’accès exchange ;
- d’inspecter l’historique des décisions ;
- de modifier les budgets ;
- d’approuver les changements d’architecture ou de risque.

Aucun agent ne peut ralentir, contourner ou réinterpréter une instruction explicite d’arrêt.

---

## 35. Hors périmètre du premier prototype

Le premier prototype n’a pas besoin de :
- high-frequency trading ;
- exécution à la milliseconde ;
- dizaines d’exchanges ;
- dizaines de cryptos ;
- retraits autonomes ;
- modification autonome des règles de risque ;
- déploiement production autonome par les agents ;
- code auto-modifié sans contrôle ;
- rentabilité garantie ;
- autofinancement immédiat de l’IA ;
- très grand nombre d’agents.

Le prototype doit privilégier :
- l’observabilité ;
- la sécurité ;
- la qualité des données ;
- la reproductibilité ;
- la robustesse.

---

## 36. Définition du succès du prototype

Le prototype est considéré comme réussi s’il sait :

1. recevoir les données de marché ;
2. détecter des opportunités candidates ;
3. déclencher le bon niveau de raisonnement IA ;
4. obtenir des analyses indépendantes des spécialistes ;
5. effectuer une revue contradictoire ;
6. produire une proposition structurée ;
7. faire accepter ou rejeter cette proposition par le Risk Engine ;
8. simuler ou exécuter le trade autorisé ;
9. enregistrer toutes les décisions et tous les coûts ;
10. calculer les performances trading et IA ;
11. respecter les budgets de risque et d’IA ;
12. échouer de manière sûre.

La rentabilité n’est évaluée sérieusement qu’une fois l’infrastructure fiable.

---

## 37. Décisions encore ouvertes

Les sujets suivants devront être tranchés au fil du développement :
- premier exchange ;
- spot ou dérivés pour la V1 ;
- symboles exacts ;
- timeframes initiaux ;
- limites de risque exactes du profil Balanced ;
- choix de base de données locale ;
- politique de rétention des données ;
- routage initial des modèles IA ;
- mécanisme de plafond du budget IA ;
- schémas structurés exacts ;
- modèle de fills / slippage paper ;
- périmètre du premier dashboard ;
- environnement de déploiement ;
- permissions exactes des clés API live.

Ces décisions doivent être prises lorsqu’elles deviennent nécessaires pour le milestone suivant.

---

## 38. Accord de travail pour le développement

Pour la suite :
- ce document reste la référence de haut niveau ;
- les spécifications détaillées seront ajoutées dans les documents de domaine ;
- la documentation restera volontairement sous la limite de fichiers disponible ;
- le code sera développé par ChatGPT par lots ou sous-lots cohérents ;
- les livrables seront fournis sous forme de ZIP prêts à intégrer dans VS Code ;
- chaque lot précisera les étapes d’installation et les fichiers modifiés ;
- les sources présentes dans le projet seront considérées comme contexte autoritatif ;
- toute divergence entre implémentation et spécification devra être documentée.

---

## 39. État actuel du projet

**Phase actuelle :** Spécification / pré-développement.

Direction générale déjà validée :
- architecture multi-agents Money Heist ;
- 100 € de capital réel initial ;
- environ 20 à 30 € de budget IA externe initial ;
- objectif long terme d’autofinancement IA ;
- un seul système LIVE au départ ;
- plusieurs profils de risque en SHADOW ;
- recrutement contrôlé de nouveaux agents ;
- Risk Engine déterministe ;
- autorité humaine sur l’arrêt et les règles de risque ;
- livraison du code par lots ZIP pour intégration locale dans VS Code ;
- documentation projet en français.

---

## 40. Prochaine étape recommandée

Créer le premier document de conception détaillé :

**`02_ARCHITECTURE.md`**

Il devra définir :
- les services ;
- les responsabilités de chaque couche ;
- le flux runtime ;
- le cycle d’orchestration des agents ;
- le stockage ;
- le modèle événementiel ;
- la séparation PAPER / SHADOW / LIVE ;
- les frontières de panne ;
- la stratégie de configuration ;
- la forme générale du déploiement.

Ensuite, nous pourrons commencer le **Lot de développement 01 — Fondations**.


---

## 41. Addendum post-Batch 16 — état implémenté

Les sections historiques décrivant le projet comme « pré-développement » sont superseded pour l’état courant par `00_ETAT_ACTUEL_POST_BATCH_15.md`, `09_ROADMAP_DEVELOPPEMENT.md`, `10_DECISIONS_ET_CHANGELOG.md` et le code sur `main`.

Le Batch 16 implémente désormais le chemin de validation décrit en section 24 :

```text
Dataset historique versionné
→ replay chronologique sans look-ahead
→ Feature Engine / Scanner de production
→ agents / Risk Engine
→ PaperBroker
→ cycle de vie positions / equity
→ Evaluation
→ DESIGN / VALIDATION / OOS
→ walk-forward V1
```

Un run historique doit identifier sa période, son dataset, les versions Feature/Scanner/Risk/Prompts/Models, sa version de code, sa version du modèle d’exécution, son seed et son mode IA.

Le moteur est une infrastructure de preuve. Sa présence ne constitue pas une preuve de profitabilité ni une autorisation LIVE. Les critères de promotion doivent être définis avant les campagnes finales et les résultats OOS doivent rester séparés des données de conception.
