# Money Heist — Backtesting & Historical Replay

**Document :** Contrat détaillé Batch 16  
**Version :** 1.1  
**Date :** 2026-09-08  
**Statut :** Référence technique active

---

## 1. Objectif

Batch 16 fournit une boucle historique end-to-end qui réutilise les composants métier de production tout en garantissant l’absence d’exécution LIVE.

```text
Historical OHLCV
→ Feature Engine
→ Scanner
→ CandidateOpportunity
→ AI Compute Gate / Orchestration
→ TradeProposal
→ Risk Engine
→ PAPER Broker
→ positions simulées
→ PnL / Equity
→ Evaluation
```

---

## 2. Invariant no-look-ahead

À l’étape temporelle `t`, aucun composant décisionnel ne peut lire une bougie postérieure à `t`.

Ordonnancement d’une bougie N :

```text
1. N open
2. résoudre les protections des positions déjà ouvertes contre N
3. N close
4. ReplayClock = close(N)
5. N devient visible pour Feature Engine / Scanner
6. orchestration / Risk / PAPER
7. une nouvelle entrée est créée à la clôture N
8. ses protections ne deviennent actives que pour les bougies futures
```

Une position créée à la clôture N ne peut donc jamais être stoppée/targetée par le high/low déjà observé de N.

---

## 3. DatasetRef

Un dataset est immuable par contenu pour un run :
- OHLCV trié ;
- timestamps UTC ;
- close_time > open_time ;
- pas de doublon d’open_time ;
- cohérence high/low/open/close ;
- volume non négatif ;
- symbole/timeframe/source ;
- bornes temporelles ;
- SHA-256 ;
- `dataset_id` et `version` stables.

Les métadonnées descriptives ne modifient pas le hash du contenu de marché.

---

## 4. BacktestConfig et run_id

Les entrées matérielles incluent :
- `system_id` ;
- `risk_version` ;
- `code_version` ;
- `execution_model_version` ;
- `random_seed` ;
- `ai_mode` ;
- capital initial ;
- maker/taker fees ;
- market slippage ;
- policy intrabar ;
- versions Feature/Scanner ;
- versions prompts/models ;
- hypothèses d’exécution additionnelles.

Le `run_id` change si l’un de ces éléments ou la période/dataset change.

Pour une campagne officielle, `code_version` devrait référencer un commit Git ou une version de build immuable.

---

## 5. PortfolioRiskState dynamique

Avant chaque décision Risk, l’état est reconstruit depuis le PaperBroker :
- equity ;
- day_start_equity ;
- equity_peak ;
- daily_pnl ;
- open_positions ;
- gross_exposure_amount ;
- open_risk_amount ;
- correlated_risk_amount.

V1 utilise une hypothèse conservatrice où le risque corrélé peut être égal au risque ouvert total en l’absence d’un modèle de corrélation plus riche.

---

## 6. Cycle de vie historique

Après une entrée PAPER autorisée :
- le stop approuvé est attaché à la position ;
- les targets de la proposition sont mémorisés ;
- l’open risk est calculé à partir de la distance entrée-stop et de la quantité ;
- les positions fermées perdent leur protection ;
- un changement de direction nettoie les protections incompatibles.

---

## 7. Policy intrabar V1

`IntrabarPolicy.STOP_FIRST` est la policy V1.

### Gap stop
Si le marché ouvre au-delà du stop dans le mauvais sens :
- référence = open historique ;
- ordre de sortie = market PaperBroker ;
- slippage market configuré appliqué.

### Gap target
Si le marché ouvre au-delà du target dans le bon sens :
- fill plafonné au target ;
- aucun gain « meilleur que target » inventé.

### Stop + target même bougie
Sans sous-bougie permettant d’ordonner les touches :
- STOP gagne.

### Target V1
- premier target favorable ;
- fermeture complète ;
- pas de scale-out partiel en V1.

Toute autre policy future doit être explicitement versionnée.

---

## 8. Modes IA

### MOCK
Client mock explicite ; adapté aux tests déterministes.

### CACHED
Cache-only. Aucune délégation upstream. Cache miss = erreur.

### LIVE_EVAL
Délégation à un client IA réel du Batch 06, avec budget AI Gateway. Peut remplir un cache si configuré.

Aucun de ces modes n’autorise l’exécution LIVE de trading.

---

## 9. Evaluation

`evaluate_historical_replay()` alimente le Batch 10 depuis :
- orders/fills PaperBroker ;
- final marks ;
- equity points ;
- pipeline results ;
- paper events optionnels ;
- AI usage records optionnels.

Le rapport Batch 10 fournit notamment :
- PnL réalisé/net ;
- fees ;
- slippage ;
- open positions ;
- unrealized PnL ;
- win rate ;
- profit factor ;
- expectancy ;
- max drawdown ;
- coûts IA ;
- métriques agents ;
- Economic Net ;
- Self-Funding Ratio.

MAE/MFE ne sont publiés que si des données suffisantes permettent de les reconstruire sans hypothèse arbitraire.

---

## 10. Fingerprint business

Le fingerprint compare les résultats business :
- compteurs ;
- snapshots/opportunités ;
- décisions Risk ;
- prix/quantités/frais des fills ;
- états de compte ;
- événements de sortie ;
- métriques Evaluation ;
- coûts IA.

Les IDs techniques aléatoires sans impact business ne doivent pas provoquer un faux échec de reproductibilité.

---

## 11. DESIGN / VALIDATION / OOS

`BacktestSplitPlan` impose trois périodes non chevauchantes :

```text
DESIGN < VALIDATION < OOS
```

Les trois restent dans le même `DatasetRef` et produisent trois `BacktestRun` distincts.

Usage :
- DESIGN : développement des hypothèses ;
- VALIDATION : vérification avant gel ;
- OOS : test hors échantillon.

Un `BacktestSplitReport` expose `out_of_sample` explicitement et ne fusionne pas les performances des trois périodes.

---

## 12. Walk-forward V1

`build_walk_forward_plan()` travaille en nombres de bougies :
- `design_bars` ;
- `validation_bars` ;
- `oos_bars` ;
- `step_bars`.

Chaque fenêtre est alignée sur les close_time réels du dataset.

Le plan produit des `BacktestRunSet` à partir d’une **configuration unique figée**.

V1 ne recherche aucun paramètre et n’expose aucun optimiseur. Si une optimisation est ajoutée plus tard, elle devra être séparée du runner et journaliser son espace de recherche pour contrôler le data snooping.

---

## 13. Exports

Exports Batch 16 :
- `BacktestRunManifest` JSON canonique ;
- split report JSON ;
- walk-forward report JSON ;
- equity curve CSV ;
- closed trades CSV.

Le manifeste contient notamment run/dataset/période/mode IA/code version/execution model/seed/fingerprint business.

---

## 14. Sécurité

Le package backtest ne dépend pas de l’exécution LIVE.

Des tests recherchent explicitement les dépendances interdites vers :
- `app.trading.live` ;
- broker LIVE Kraken ;
- service d’exécution LIVE ;
- méthodes d’ordre LIVE/privé.

Le Risk Engine n’est jamais bypassé pour créer une entrée historique issue d’une proposition agents.

---

## 15. Procédure de campagne recommandée

1. sélectionner et figer le dataset ;
2. documenter qualité/gaps/source/timeframe ;
3. définir les périodes DESIGN/VALIDATION/OOS ;
4. figer `BacktestConfig` et `code_version` ;
5. choisir MOCK/CACHED/LIVE_EVAL ;
6. exécuter le replay ;
7. générer Evaluation + manifeste + fingerprint ;
8. répéter le même run et vérifier le fingerprint ;
9. analyser VALIDATION ;
10. ne consulter OOS qu’après gel des choix ;
11. exécuter walk-forward ;
12. comparer OOS des fenêtres ;
13. poursuivre PAPER/SHADOW ;
14. ne passer au preflight LIVE qu’après critères prédéfinis satisfaits.

---

## 16. Ce que Batch 16 ne fait pas

Batch 16 ne :
- garantit aucune rentabilité ;
- choisit pas automatiquement les meilleurs paramètres ;
- ne fixe pas les seuils de promotion LIVE ;
- ne remplace pas PAPER/SHADOW ;
- ne crée pas de chemin d’ordre LIVE ;
- n’arme pas le Batch 15 ;
- n’invente pas MAE/MFE ou statistiques indisponibles.

---

## 17. Gate finale

La gate avant capital réel reste une décision d’exploitation fondée sur des preuves :

```text
Backtest reproductible
+ OOS
+ walk-forward
+ PAPER/SHADOW
+ configuration Risk complète
+ Market Data production validé
+ sécurité/preflight
+ décision opérateur
```

---

## 18. Extension Batch 16.7 — Backtest Dashboard

Le Batch 16.7 ajoute une interface opérateur au moteur historique sans créer un second moteur de backtest.

Chemin :

```text
/dashboard/backtest
→ validation CSV / DatasetRef
→ configuration BacktestConfig + RiskProfile + MarketConstraints
→ DESIGN / VALIDATION / OOS
→ HistoricalReplayRunner
→ PaperTradingPipeline / RiskEngine / PaperBroker
→ Evaluation / exports
```

Principes :
- le Dashboard V1 SHADOW existant reste read-only ;
- le Backtest Dashboard peut déclencher uniquement des simulations historiques PAPER ;
- aucune route du Dashboard backtest n'importe l'exécution LIVE ;
- `LIVE_EVAL` ne rend réel que le fournisseur IA ;
- `OPENAI_API_KEY` est lue uniquement dans l'environnement backend et n'est jamais saisie dans le navigateur ;
- les contraintes marché restent explicites et ne sont pas inventées par l'interface ;
- les valeurs Risk, MarketConstraints, budget/pricing IA sont injectées dans les hypothèses versionnées du run Dashboard afin de modifier son identité si elles changent ;
- le profil de risque prérempli est un exemple DEV, pas un profil LIVE approuvé ;
- l'historique des campagnes est en mémoire et borné pour cette V1 ;
- les exports JSON/CSV Batch 16 sont téléchargeables depuis l'interface.

### Cache IA V2

Le cache `money-heist.backtest-ai-cache.v2` exclut le `request_id` fournisseur de sa clé et utilise un scope d'expérience qui ignore uniquement le choix `ai_mode`. Cela permet à un run `LIVE_EVAL` de remplir un cache ensuite rejouable en `CACHED` avec le même dataset, la même période et la même configuration matérielle.

Les versions prompts/modèles et le contenu de requête restent dans la clé. Un cache miss en mode `CACHED` reste fail-closed.



## 19. Extension Batch 17a — Denver et statistiques historiques de setup

Batch 17a ajoute une couche statistique au-dessus des sorties Batch 16 sans modifier
`HistoricalReplayRunner`.

Flux :

```text
Runs Batch 16 terminés
→ trades PAPER fermés + opportunités exécutées
→ attribution stricte au setup Scanner/régime
→ HistoricalSetupStatsCatalog content-addressed
→ query as_of
→ DenverContext
→ Denver ON_DEMAND dans OrchestrationPipeline
```

Le catalogue n’est pas une mémoire mutable implicite du runner. Pour un backtest reproductible, son
identité et la version de définition du setup doivent être liées aux `execution_assumptions` du run.
Le provider `DenverSetupStatsContextProvider.for_backtest(...)` refuse un binding absent ou
incohérent.

Le MOCK avancé est un wrapper du provider MOCK existant : tous les schémas legacy sont délégués
sans modification. En l’absence de contexte Rio/Denver, le plan legacy reste identique.

Cette extension ne constitue pas un optimiseur, ne réalise pas d’ablation, ne calcule pas une
réputation agent et n’active aucun chemin LIVE.

## 20. Extension Batch 17b — frontière historique de Rio

Le Batch 17b active Rio avec des analytics Kraken Futures courants pour PAPER/SHADOW, mais ne les
injecte pas dans `HistoricalReplayRunner`.

Cette séparation est volontaire : un snapshot analytics obtenu aujourd'hui ne peut pas être utilisé
comme s'il avait été disponible au timestamp d'une bougie historique. Le replay Rio futur devra donc
consommer un dataset dérivés historique content-addressed avec timestamps, provenance et règles de
fraîcheur adaptées au replay.

Denver reste le spécialiste avancé directement exploitable avec les preuves historiques Batch 16.
Rio reste exploitable sur flux courant jusqu'à livraison d'une source historique dérivés dédiée.
