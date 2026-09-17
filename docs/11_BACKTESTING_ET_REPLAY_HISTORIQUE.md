# Money Heist — Backtesting & Historical Replay

**Document :** Contrat détaillé Batch 16  
**Version :** 1.4
**Date :** 2026-09-16
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

---

## 18.1. Smoke LIVE_EVAL de référence — validation technique

Référence validée le 2026-09-11 :
- code version : `294cfa2547f94c9694fdc65758c3f9435ff55dd2` ;
- campagne : `177add07-b684-440c-b8ca-a37313a6eac5` ;
- dataset : `BTC/USDC:1h:4f5515aef296533f` ;
- progression : `345/345` ;
- opportunités : `15` ;
- Professor FINAL : `14 NO_TRADE`, `1 SHORT` ;
- Risk Engine : `RESIZED` ;
- quantité approuvée : `0.00156 BTC` ;
- risque approuvé : `0.7306260` ;
- notionnel approuvé : `99.4993740` ;
- ordres PAPER exécutés : `1` ;
- échecs techniques : `0`.

Ce smoke démontre que le chemin suivant est opérationnel avec un fournisseur IA réel :

```text
OHLCV historique
→ Feature Engine
→ Scanner
→ CandidateOpportunity
→ AI Gateway / Professor / spécialistes / Palermo
→ Professor FINAL
→ TradeProposal
→ Risk Engine déterministe
→ PaperBroker
```

Les sous-lots de robustesse 16.12 à 16.20 ont notamment fermé les défauts observés sur schémas
structured output, grounding, accounting des réponses incomplètes, timeout/headroom Palermo et
alignement Professor/Compute Gate.

La validation reste **technique**. Elle ne signifie pas que la stratégie est rentable ou robuste.
Une campagne longue doit encore couvrir plusieurs régimes et produire des preuves séparées
DESIGN/VALIDATION/OOS, walk-forward, coûts IA et comportement PAPER/SHADOW.

---

## 19. Extension Batch 19 — campagnes d'évaluation Recruitment

Le Recruitment Engine réutilise le moteur Batch 16 pour comparer un candidat à une baseline sans créer un second runner.

```text
RecruitmentCampaignPlan
├─ BASELINE
│  → HistoricalReplayRunner / PAPER isolé
└─ WITH_CANDIDATE
   → HistoricalReplayRunner / PAPER isolé
```

Les twins doivent partager dataset, période, rôle, configuration matérielle et crew incumbent. Les `run_id` sont distincts et les runners/brokers PAPER ne peuvent pas être réutilisés entre variants.

Le rôle de période reste explicite :
- `DESIGN` / `VALIDATION` : diagnostic possible ;
- `OOS` : requis pour une preuve utilisable par l'advisory de promotion.

Le gate de comparabilité vérifie notamment dataset, bornes temporelles, rôle, candles traitées, opportunités, configuration et roster. La provenance conserve les run ids, business fingerprints et fingerprints de campagne/critères.

Le résultat Recruitment peut être adapté vers l'ablation Batch 18 en considérant `WITH_CANDIDATE` comme le système complet et `BASELINE` comme le twin sans candidat. Cette adaptation ne modifie ni le runner, ni le Risk Engine, ni les métriques Batch 18.

Aucune campagne Recruitment historique ne peut :
- créer un ordre LIVE ;
- armer le Batch 15 ;
- muter `AgentRegistry` ;
- appliquer automatiquement une promotion.

<!-- BATCH20_REPLAY_START -->

## Addendum Batch 20 — Replay Task Force

Batch 20e réutilise le moteur Batch 16 pour comparer une opportunité avec et sans Task Force :

```text
BASELINE
vs
WITH_TASK_FORCE
```

Les deux variantes partagent dataset, rôle, période et configuration matérielle, mais possèdent des
`run_id` distincts via des `execution_assumptions` réservées. Chaque variante reçoit un runner et un
PaperBroker isolés.

La baseline doit produire zéro artefact Task Force. Le treatment doit produire exactement un
`TaskForceReport` et son exécution correspondante pour l’opportunité ciblée. Le report et son
agrégation doivent rester dans les bornes temporelles du replay.

Un seal final capture les business fingerprints baseline/treatment ainsi que les fingerprints Task
Force. Toute dérive matérielle rend l’audit `STALE`. Le mécanisme reste PAPER-only, y compris
lorsque
le mode IA du backtest utilise un fournisseur réel pour l’évaluation.

<!-- BATCH20_REPLAY_END -->

<!-- BATCH22_FRONTEND_V2 -->
## Extension Batch 22 — Historical Replay visuel

Frontend V2 fournit un workspace de replay sans créer de second moteur historique. Pour les campagnes lancées via l'endpoint V2, un sidecar borné conserve la requête immuable et agrège les `AgentTraceView` déjà émises pendant l'exécution. Après le run, le replay combine : candles du dataset original, traces agents/Risk, exports closed-trades, exports equity.

Le frontend respecte donc l'ordre du Batch 16 et ne résout jamais lui-même l'intrabar, le STOP_FIRST, les gaps, les fees/slippage ou le lifecycle des positions. Les périodes DESIGN, VALIDATION et OOS restent séparées.

Limitation V1 : le Dashboard Backtest historique reste en mémoire et `CampaignSummary` ne conserve pas le CSV brut ; un replay visuel détaillé n'est donc garanti que pour les campagnes démarrées via Frontend V2 pendant la vie du même processus. Cette limitation doit être supprimée par une future persistance durable des campagnes/datasets/traces, pas par une reconstruction côté navigateur.

<!-- BATCH22_1_BACKTEST_COCKPIT -->
## Extension Batch 22.1 — Backtest Cockpit et replay durable

Le cockpit expose explicitement split, Risk, IA, exécution et Walk-Forward. Un dataset validé est persisté une fois puis référencé par `dataset_id`. À la fin d'une campagne, Frontend V2 snapshotte résumé, traces et exports existants afin de restaurer le replay après redémarrage, sans réexécution du moteur historique.

<!-- DOC_REALIGN_REPLAY_CACHE_DISTINCTION_START -->

## Addendum 2026-09-15 — deux caches distincts

Money Heist possède désormais deux mécanismes à ne pas confondre :

```text
OpenAI Prompt Cache
→ nouvel appel fournisseur
→ réutilisation éventuelle du préfixe stable
→ réponse recalculée

money-heist.backtest-ai-cache.v2
→ mode CACHED Money Heist
→ aucune délégation fournisseur
→ réponse complète rejouée
→ cache miss fail-closed
```

La policy Prompt Cache et `prompt_render_version` font partie des hypothèses versionnées d’une campagne lorsque le Dashboard/Frontend les expose. La persistance Batch 22.1 supersède la limitation historique « campagne seulement en mémoire » pour les campagnes V2 : dataset, configuration, progression/traces, résumé et exports nécessaires au replay sont persistés dans le sidecar local.

<!-- DOC_REALIGN_REPLAY_CACHE_DISTINCTION_END -->

<!-- BATCH23A1_REPLAY_DECISION_FUNNEL -->
## Extension Batch 23A.1 — Decision Funnel Baseline

Batch 23A.1 ajoute une couche de mesure causale après le replay sans modifier le chemin de décision.

Le runner conserve deux compteurs pré-Scanner :
- `pre_scanner_warmup_skipped` ;
- `pre_scanner_not_decision_close_skipped`.

Les points effectivement scannés sont ensuite agrégés en :
- `scanner_evaluations`, `scanner_no_trigger`, `scanner_triggered` ;
- `candidate_opportunities` ;
- Compute Gate allowed/blocked ;
- orchestrations IA déclenchées ;
- Professor PLAN `NO_ANALYSIS` et Professor FINAL `NO_TRADE` ;
- propositions créées ;
- décisions Risk `REJECTED`, `RESIZED`, `APPROVED` ;
- ordres soumis et fills.

Les événements/causes sont agrégés sous forme de reason codes déterministes. `closed_trades`, nombre total d'ordres broker et nombre total de fills broker sont placés dans `post_hoc`, car ils sont postérieurs à la décision initiale.

Invariants :
```text
candles_evaluated
= pre_scanner_warmup_skipped
+ pre_scanner_not_decision_close_skipped
+ scanner_evaluations

scanner_evaluations
= scanner_no_trigger
+ scanner_triggered
```

Le `DecisionFunnelReport` :
- ne déclenche aucun appel Scanner/IA/Risk/broker ;
- n'entre jamais dans `DecisionContext` ;
- ne modifie pas `BacktestConfig` ni `run_id` ;
- ne modifie pas le fingerprint business historique ;
- est exporté par période sous `*-decision-funnel.json`.

**Commit de référence :** `fbec1d3fadaf811c6e84d33741aa08166cc472cd`.

<!-- BATCH23A2_4_REPLAY_MEASUREMENT -->
## Extension Batch 23A.2 — Forward Outcomes

Batch 23A.2 calcule post-hoc, pour chaque `CandidateOpportunity`, les horizons :

```text
H1 / H3 / H5 / H10 / H20
```

Ils sont exprimés dans le timeframe de décision, même lorsque le dataset source utilise un timeframe plus fin.

Référence : close du `FeatureSnapshot` au temps de l'opportunité.

Pour un horizon complet :
- rendement close-to-close ;
- max-upside ;
- max-downside ;
- timestamps des extrema ;
- first-hit `MAX_UPSIDE`, `MAX_DOWNSIDE` ou `SAME_CANDLE`.

Pour un horizon incomplet :
- nombre de barres observées ;
- gaps ;
- barres manquantes à cause de `period_end` ;
- raison `GAP`, `PERIOD_END` ou `GAP_AND_PERIOD_END` ;
- aucune métrique de prix partielle.

Les outcomes ne franchissent jamais la frontière du split courant.

**Commit de référence :** `b78266efe5c0bf203d75348907cac5000472e9c6`.

## Extension Batch 23A.3 — Funnel Outcome Attribution

Batch 23A.3 croise les Forward Outcomes candidats avec les sorties déjà émises par le pipeline.

Dimensions :
- statut terminal ;
- régime ;
- trigger Scanner ;
- Compute Gate reason ;
- Professor PLAN ;
- agent sélectionné ;
- échec orchestration ;
- Professor FINAL direction ;
- proposal side ;
- Risk status / reason ;
- Paper Pipeline failure.

Les statistiques directionnelles utilisent `TradeProposal.side` si disponible, sinon Professor FINAL LONG/SHORT. `NO_TRADE` n'est pas artificiellement transformé en direction.

Les dimensions multi-valuées restent chevauchantes. Le rapport est descriptif et ne choisit aucun seuil.

**Commit de référence :** `42903cce9e694fdf1f23923fdba0708176e7775a`.

## Extension Batch 23A.4 — Scanner Forward Outcomes

Batch 23A.4 couvre aussi les évaluations Scanner qui n'ont jamais produit de candidat.

Invariant principal :

```text
scanner_evaluations
=
scanner_no_trigger
+ trigger_below_candidate_threshold
+ candidate_opportunities
```

avec également :

```text
scanner_triggered
=
trigger_below_candidate_threshold
+ candidate_opportunities
```

Chaque record conserve :
- score Scanner exact ;
- `min_priority_score` réellement utilisé ;
- marge score - seuil ;
- triggers ;
- régime ;
- éventuel `candidate_opportunity_id` ;
- mêmes horizons H1/H3/H5/H10/H20 que Batch 23A.2.

23A.4 lit le `ScanResult` déjà présent dans `HistoricalReplayResult`. Il ne rappelle jamais `DeterministicScanner`.

**Commit de référence :** `611bef38f9e056ea7d7964a0f10191bac58551e4`.

## Exports 23A consolidés

Chaque split DESIGN / VALIDATION / OOS peut produire :

```text
*-decision-funnel.json
*-forward-outcomes.json
*-funnel-outcome-attribution.json
*-scanner-forward-outcomes.json
```

Ces exports sont post-hoc/observationnels. Ils ne modifient ni `BacktestConfig`, ni `run_id`, ni le fingerprint business, ni le chemin de décision.

## Utilisation attendue

La pile 23A est maintenant suffisante pour lancer des campagnes longues multi-régimes et examiner quantitativement :

- où les opportunités sont filtrées ;
- ce que deviennent les candidats acceptés/refusés ;
- ce que deviennent les triggers sous seuil ;
- comment les distributions varient par score, trigger et régime.

Toute hypothèse de tuning issue de cette analyse doit être formulée comme une expérience distincte et validée sur VALIDATION/OOS avant d'être envisagée pour PAPER/SHADOW, puis éventuellement LIVE.
<!-- BATCH24A1_REPLAY -->
## Dérivation Analytics Lab (Batch 24A.1)

Un `AnalyticsLabRun` dérive d'un `BacktestRun` existant sans rerun du Scanner ni
des agents. L'adaptateur conserve `DatasetRef`, bornes de période, rôle
DESIGN/VALIDATION/OOS, politique MTF et `source_cursor_fingerprint` de l'univers
visible. Les versions Analytics produisent uniquement une nouvelle identité
Analytics.

Les Forward Outcomes 23A ne sont pas consommés par `app.analytics`; une future
jointure décision + Analytics + outcomes appartiendra à une couche d'attribution
séparée.

<!-- BATCH_24A2_RICH_INDICATORS -->
### Batch 24A.2 — projection indicateurs au replay

Le moteur Analytics Indicators consomme les bougies closes du `HistoricalMultiTimeframeCursor` / `HistoricalMultiTimeframeSlice`; il ne resample pas et n'ingère aucune donnée lui-même. À T, seules les bougies dont `close_time <= as_of` peuvent contribuer. Le `source_cursor_fingerprint` est conservé dans le snapshot Indicators.

<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Addendum Batch 24A.3 — événements Analytics pendant le replay

Les Technical Events peuvent être reconstruits causalement à partir des snapshots
Indicators visibles à T-1/T. La propriété attendue reste :

```text
Events(full_dataset, as_of=T) == Events(dataset_truncated_at_T, as_of=T)
```

Les événements Analytics participent à l'identité/fingerprint Analytics, mais ni au
`BacktestRun.run_id` ni au business fingerprint. Une candle future malformée ne doit pas
modifier un événement déjà disponible à T et une candle higher-timeframe non close ne doit
produire aucun événement de ce timeframe.

<!-- BATCH_24A4_CAUSAL_STRUCTURE_ZIGZAG -->
## Batch 24A.4 — causalité structurelle

Le ZigZag consomme exclusivement des candles closes déjà visibles dans le replay et
l'ATR14 produit par Analytics Indicators. Pour tout `as_of=T`, seuls les pivots avec
`confirmed_at <= T` sont exposés. Un suffixe futur ne peut modifier les pivots déjà
confirmés visibles à T.

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
## Addendum Batch 24A.7 — replay causal des recherches

La résolution Context/Sequence respecte l'invariant prefix : à `as_of=T`, le résultat est identique avec le dataset complet ou tronqué à T. Les anchors utilisent leurs timestamps de disponibilité (`available_at` / `confirmed_at`) et une séquence complétée ultérieurement n'est jamais rétro-propagée dans un snapshot antérieur.

<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Addendum Batch 24B.1 — jointure post-hoc après replay

Après un `HistoricalReplayResult` complété et un `AnalyticsLabRun` complété sur le
même univers,
24B.1 adapte les points ayant une `CandidateOpportunity` vers un
`DecisionObservationKey`.
`HistoricalReplayPoint.mtf_cursor_fingerprint` fournit la preuve de préfixe causal
même si
l'opportunité ne possède pas de `DecisionContext`.

Le lookup Analytics est exact sur `(symbol, decision_timeframe, as_of)` à
l'intérieur d'un
`analytics_run_id` explicitement fourni. Un snapshot précédent ou futur n'est
jamais choisi.
Deux snapshots distincts portant la même clé canonique produisent
`AMBIGUOUS_ANALYTICS_SNAPSHOT`.
Le linker ne lance aucun Indicator/Event/ZigZag/Pattern/Context/Sequence resolver
et ne rejoue
aucun Scanner/agent/Risk.

<!-- BATCH_24B2_DECISION_INTELLIGENCE_RECORD -->
## Addendum Batch 24B.2 — projection Decision Intelligence après replay

Après un replay terminé et la construction des links 24B.1, 24B.2 peut produire un record par
`CandidateOpportunity` depuis les `HistoricalReplayPoint` déjà présents. Cette opération est
purement dérivée : elle ne relance ni Scanner, ni orchestration, ni Risk, ni broker et ne modifie
pas `BacktestRun.run_id` ou le fingerprint business. Les résultats futurs et `exit_events` ne
font pas partie du core record causal.

<!-- BATCH_24B3_SCANNER_ANALYTICS_ATTRIBUTION -->
## Addendum Batch 24B.3 — attribution Scanner après replay

Après un Historical Replay terminé, 24B.3 projette les `FeatureSnapshot` et `ScanResult` déjà
présents en `ScannerObservation`, puis résout le `AnalyticsSnapshot` exact au même `as_of` avec
le même `source_cursor_fingerprint`. Le Scanner n'est jamais relancé et aucune donnée future
n'est utilisée pour sélectionner un snapshot Analytics.
