# Money Heist — Frontend et Interface V2

**Document :** Référence fonctionnelle et technique du Frontend V2  
**Version :** 1.4
**Date :** 2026-09-19
**Statut :** Frontend V2 — Backtest Cockpit, résumé opérateur, Decision Intelligence et Research Explorer 24D.4
**Baseline auditée :** `35f736d41e1d110bb456005a6c8df77a651e069a`

---

## 1. Objectif du Frontend

Le Frontend V2 transforme le Dashboard V1 en cockpit d’observabilité et d’audit. Il rend visible la chaîne :

```text
MARKET → FEATURES → SCANNER → OPPORTUNITY → CREW → PROFESSOR
→ PALERMO → TRADE PROPOSAL → RISK ENGINE → ORDER → FILL → POSITION → RESULT
```

Il ne devient jamais une nouvelle autorité métier. Le backend Python/FastAPI reste la source de vérité pour les décisions, le risque, l’exécution et le backtest.

## 2. Architecture

```text
Browser / Next.js
  → route proxy Next server-side `/api/money-heist/*`
  → FastAPI Money Heist
  → services existants
```

Le proxy évite d’exposer un secret dans le navigateur et permet de conserver une seule origine côté UI. Le frontend est un sous-projet séparé sous `frontend/`.

## 3. Stack

- Next.js App Router ;
- React ;
- TypeScript strict ;
- Tailwind CSS ;
- composants inspirés shadcn/ui via Radix ;
- Lucide ;
- TanStack Query pour le server state ;
- Zod pour la validation runtime ;
- Zustand uniquement pour préférences UI ;
- TradingView Lightweight Charts derrière `TradingChartAdapter`.

La Charting Library propriétaire TradingView n’est pas incluse : aucune licence n’a été constatée dans le dépôt audité.

## 4. Frontières backend/frontend

Le frontend ne calcule pas les indicateurs de production, ne crée pas de `CandidateOpportunity`, ne produit pas de `TradeProposal`, ne fait pas de sizing, ne valide pas le risque et ne recalcule pas un replay historique.

Les actions critiques non exposées par une API backend sécurisée ne reçoivent aucun bouton factice. L’état `LIVE_DISABLED / LIVE_PREFLIGHT / LIVE_ARMED` existe dans le backend Batch 15, mais aucune API HTTP opérateur correspondante n’était présente dans la baseline auditée ; Frontend V2 affiche donc l’armement comme non exposé.

## 5. Navigation

Routes principales :

```text
/dashboard
/trading
/backtests
/backtests/{campaign_id}
/opportunities
/orders
/positions
/history
/agents
/evaluation
```

Les réglages sont ouverts dans une modale globale. La navigation desktop se réduit ; la navigation mobile devient un drawer.

## 6. Layout et sidebars

Desktop : sidebar gauche + workspace + inspector contextuel lorsque la page le nécessite. Le Trading Workspace et le Historical Replay utilisent un inspector droit. Sur mobile, la sidebar devient un drawer et les tables restent scrollables horizontalement.

## 7. Trading Workspace

Le Trading Workspace affiche : système par défaut, mode runtime, symbole, timeframe, candles Kraken publiques, opportunités observables, décision Professor et RiskDecision. Les symboles et timeframes proviennent des capacités backend.

Le Dashboard V1 reste la source des objets SHADOW/PAPER observés ; le nouveau workspace ne modifie pas la logique de projection du backend.

## 8. Trading Chart

`TradingChart` délègue à `TradingChartAdapter`, actuellement implémenté avec Lightweight Charts. Les candles viennent uniquement de `/api/frontend/v2/market/candles`, qui réutilise `KrakenPublicMarketDataProvider`.

Les overlays représentent distinctement opportunité, décision, Risk, entrée et sortie. La couleur n’est pas le seul signal : forme et texte diffèrent également.

## 9. Decision Trace

Le backtest existant émet déjà des `AgentTraceView` pour :

```text
Professor PLAN
Specialists ANALYSIS
Palermo RED_TEAM
Professor FINAL
Risk Engine RISK
```

Frontend V2 les capture pendant une campagne lancée via son endpoint V2, sans modifier le moteur historique. Le Replay Inspector agrège ces traces pour expliquer la décision et les `NO_TRADE` lorsque la trace les contient.

## 10. PAPER / SHADOW / LIVE

- PAPER : données du PaperBroker et Dashboard existants ;
- SHADOW : systèmes du Dashboard V1, portefeuilles isolés ;
- LIVE : aucune commande UI créée sans API opérateur backend ;
- BACKTEST : moteur Batch 16 PAPER-only.

Le premier chemin LIVE Kraken Spot/EUR reste sans entrée SHORT. Frontend V2 ne change pas cette règle.

## 11. Backtests

La page Backtests conserve `BacktestDashboardService` comme moteur unique. Batch 22.1 transforme le lanceur en cockpit guidé :

```text
Dataset → Périodes → Risk → IA → Exécution → Données avancées → Walk-Forward → Revue
```

Les paramètres auparavant implicites sont maintenant visibles et modifiables : capital initial, frais maker/taker, slippage, Risk Profile, limites de risque, contraintes marché, mode IA, modèle, reasoning effort, budget IA, tarification, `code_version`, `execution_model_version`, seed et Walk-Forward.

Le `code_version` reste obligatoire. Les valeurs proposées à l'ouverture sont des valeurs DEV/PAPER historiques, jamais des limites LIVE approuvées.

Une bibliothèque de datasets V2 persistés permet de valider/importer un CSV une fois puis de le réutiliser pour plusieurs campagnes sans réupload navigateur.

Le cockpit peut également découvrir la bibliothèque locale de préfixes générée par
`scripts/market_data/build_campaign_prefix_datasets.py`. Les durées 1 / 3 / 6 / 9 / 12 mois
sont lues depuis `data/historical/binance_spot/campaign_datasets/campaign_datasets_manifest.json`.
Le navigateur ne reçoit jamais de chemin filesystem : il ne voit que les métadonnées du manifeste.
Lorsqu'un opérateur sélectionne une durée, le backend relit le fichier local, vérifie taille et
SHA-256 contre le manifeste, le revalide avec `BacktestDashboardService`, puis l’enregistre dans la
bibliothèque V2 canonique avant tout lancement. L'upload CSV manuel reste disponible comme fallback.

<!-- BACKTEST_CALENDAR_WINDOW_20260920 -->
### Fenêtre calendaire de campagne

Le cockpit sépare désormais la **durée de campagne** de sa **date de début**.

L'opérateur sélectionne une source historique suffisamment longue, puis choisit :

- une date de début ;
- une durée de 1 / 3 / 6 / 9 / 12 mois calendaires ;
- le split DESIGN / VALIDATION / OOS reste 60 / 20 / 20 à l'intérieur de cette fenêtre.

La fin est calculée en mois calendaires réels et non en nombre fixe de jours. Le navigateur
utilise l'axe `candle_close_ms` fourni par le backend pour convertir la fenêtre en indices.
Le backend revalide ensuite les `SplitInput` comme auparavant.

Le dataset source n'est pas tronqué au début de la fenêtre : Historical Replay conserve les
candles antérieures à `period_start` comme contexte causal / warm-up. Pour une fenêtre datée
arbitraire, l'opérateur doit donc privilégier la source locale la plus longue qui couvre la
période, actuellement le dataset canonique 12 mois. Les préfixes 1/3/6/9 mois restent
compatibles mais ne sont plus nécessaires pour définir la durée d'une campagne.

Si la fenêtre dépasse la couverture disponible, le frontend échoue explicitement et demande
une source plus longue ; il ne fabrique pas de candles et ne télécharge aucune donnée
implicitement.

## 12. Historical Replay

Le replay V2 assemble, après exécution :

```text
Dataset persistant référencé par dataset_id
+ configuration figée de campagne
+ traces existantes agents/Risk
+ exports closed-trades existants
+ exports equity existants
```

Le navigateur ne repasse jamais le Scanner, les agents ou le Risk Engine. Batch 22.1 ajoute un sidecar durable sous `.money-heist/frontend-v2/` (surcharge possible avec `MONEY_HEIST_FRONTEND_V2_STORAGE_DIR`) qui persiste uniquement les entrées immuables et sorties déjà produites par le moteur. Le CSV est stocké une fois dans la bibliothèque de datasets puis référencé par les campagnes.

Les campagnes historiques créées avant cette persistance peuvent rester limitées au résumé/exports disponibles dans leur runtime d'origine.

## 13. DESIGN / VALIDATION / OOS

Le lanceur expose les bornes de DESIGN, VALIDATION et OOS en indices de bougies alignés sur les `close_time` réels renvoyés par le backend. Le split suggéré reste le point de départ, mais l'opérateur peut le modifier avant lancement. La validation impose `DESIGN < VALIDATION < OOS` sans chevauchement.

Après une campagne terminée, la page détail sépare désormais deux niveaux de lecture sans dupliquer les données métier :

```text
Résumé (défaut)
→ identité dataset / mode / capability
→ comparaison homogène DESIGN / VALIDATION / OOS
→ trading net, rendement de présentation, drawdown, trades, win rate, profit factor, coût IA
→ Decision Funnel compact déjà produit par le backend
→ equity OOS persistée

Analyse avancée (à la demande)
→ diagnostics techniques d'exécution
→ configuration figée
→ replay causal complet
→ overlays Analytics
→ Decision Intelligence Inspector
→ Research Explorer 24D
→ trades / events / equity par période
```

Le résumé ne relance jamais le replay et ne recalcule aucun Scanner, agent, Risk ou Forward Outcome. Le `decision_funnel` déjà présent dans `PeriodSummary` est conservé par le contrat Zod frontend au lieu d'être ignoré. Le rendement net affiché dans la vue Résumé est uniquement un ratio de présentation `trading_net / initial_balance`.

Dans l'analyse avancée, les trois périodes restent sélectionnables séparément. OOS porte explicitement le label `OUT-OF-SAMPLE`; aucune métrique globale ne fusionne DESIGN, VALIDATION et OOS.

## 14. Walk-forward

Le Walk-Forward V1 est désormais pilotable depuis le cockpit avec `design_bars`, `validation_bars`, `oos_bars` et `step_bars`. Le frontend vérifie que la fenêtre demandée tient dans le dataset avant soumission, puis le backend revalide le payload.

Le fonctionnement reste celui du Batch 16 : configuration unique figée, fenêtres alignées sur les bougies, aucun optimiseur automatique et aucun data snooping ajouté par le frontend.

## 15. Agents

La page Agents utilise le registry retourné par `/api/dashboard/backtest/capabilities`, et non une liste fermée dans le frontend. Elle peut donc afficher les agents ajoutés par les Batchs ultérieurs. Les coûts observables proviennent du Dashboard/Evaluation.

## 16. Risk

`TradeProposal` et `RiskDecision` restent des objets séparés dans l’Inspector. Les statuts APPROVED/REJECTED/RESIZED et `reason_codes` sont conservés. Les garde-fous constitutionnels sont read-only dans la modale tant qu’aucune API d’écriture sécurisée ne les expose.

## 17. Settings

Onglets livrés : Général, Marché, Trading, Agents / IA, Risque, Backtest, Interface. Un réglage sans endpoint backend d’écriture reste en lecture seule. Aucun secret exchange/OpenAI n’est demandé ou conservé dans le navigateur.

## 18. API integration

L’accès HTTP est centralisé dans `frontend/src/lib/api`. Les réponses critiques sont validées avec Zod. Une rupture de contrat déclenche `ApiContractError` au lieu de produire une interface incohérente.

Extensions backend V2 :

```text
GET  /api/frontend/v2/capabilities
GET  /api/frontend/v2/market/candles
GET  /api/frontend/v2/market/constraints
GET  /api/frontend/v2/backtests/datasets
GET  /api/frontend/v2/backtests/dataset?dataset_id=...
POST /api/frontend/v2/backtests/datasets
GET  /api/frontend/v2/backtests/local-campaign-datasets
POST /api/frontend/v2/backtests/local-campaign-datasets/{duration_months}/import
GET  /api/frontend/v2/backtests/runs
POST /api/frontend/v2/backtests/runs
POST /api/frontend/v2/backtests/runs/from-dataset
GET  /api/frontend/v2/backtests/runs/{campaign_id}
GET  /api/frontend/v2/backtests/runs/{campaign_id}/progress
GET  /api/frontend/v2/backtests/runs/{campaign_id}/configuration
GET  /api/frontend/v2/backtests/runs/{campaign_id}/replay
```

Elles réutilisent les services existants et n’exposent aucun secret ou chemin d’ordre LIVE.

## 19. Temps réel

Aucun WebSocket/SSE opérateur n’a été trouvé dans la baseline auditée. Le choix V2 est donc un polling centralisé via TanStack Query. Cette décision est volontairement minimale. Une migration WebSocket future devra conserver un manager unique et un normalizer d’événements.

Pour que ce polling reste fiable pendant les campagnes longues, les étapes CPU post-replay (23A, exports, Analytics/Decision Intelligence/Research 24A → 24D) sont exécutées hors de l'event loop FastAPI. Le frontend ne compense pas un backend bloqué par des timeouts plus longs : `/progress` et `/capabilities` doivent rester réactifs pendant le calcul.

## 20. Sécurité

- aucun secret dans `NEXT_PUBLIC_*` ;
- aucun secret en localStorage ;
- aucune API key dans les formulaires ;
- aucun optimistic update d’une action critique ;
- aucun armement LIVE côté client ;
- aucune nouvelle dépendance du backtest vers `app.trading.live` ;
- replay historique uniquement à partir des résultats PAPER déjà produits.

## 21. State management

```text
Server state       → TanStack Query
URL/routing         → Next App Router
Local UI            → React
Préférences UI      → Zustand
Backend truth       → FastAPI
```

Zustand ne contient aucune donnée métier de trading.

## 22. Tests

Priorités couvertes dans le lot : contrat API critique, mapping événements chart, logique du curseur replay, capacités frontend fail-closed et routes backend V2. Playwright contient un smoke de la modale Settings et vérifie que l’interface ne demande pas d’API key.

## 23. Conventions UI

La hiérarchie d'information distingue désormais le **pilotage** de l'**investigation** : le Résumé est la vue post-campagne par défaut et l'Analyse avancée est explicitement ouverte par l'opérateur. Les identifiants techniques complets, fingerprints, timings et outils Research ne dominent plus la lecture initiale.

Dark-first, densité élevée, composants compacts, badges sémantiques, focus visible et navigation clavier assurée par les primitives Radix là où elles sont utilisées. LONG/SHORT/Risk/Warning disposent de texte et formes distinctes ; aucune information critique ne dépend uniquement d’une couleur.

Montants et timestamps sont formatés pour l’affichage uniquement. Les valeurs brutes du backend restent conservées comme chaînes lorsque leur précision est matérielle.

## 24. Limitations

- polling au lieu de WebSocket/SSE ;
- état d’armement LIVE non exposé par l’API courante ;
- Settings principalement read-only hors lancement/configuration backtest ;
- la persistance Batch 22.1 est un sidecar fichier local V2, pas encore le stockage SQL unifié de tous les artefacts Batch 16 ;
- une campagne interrompue brutalement peut ne conserver que le dernier snapshot de progression/traces écrit avant l'arrêt ;
- les campagnes antérieures au Batch 22.1 ne gagnent pas rétroactivement le dataset brut absent ;
- Lightweight Charts utilisé à la place de la bibliothèque TradingView propriétaire ;
- l’Inspector LIVE/PAPER dépend des objets réellement projetés par Dashboard V1 et n’invente aucun contexte absent.

## 25. Evolution future

Ordre recommandé : migrer le sidecar V2 vers le stockage SQL unifié si nécessaire, ajouter une API opérateur de capacités LIVE strictement sécurisée, un flux événementiel backend unique (SSE/WebSocket si nécessaire), enrichir positions/fills, améliorer les vues walk-forward comparatives et atteindre la parité complète du `DecisionContext` LIVE ↔ Historical Replay.

---

## Matrice de migration Dashboard V1 → Frontend V2

| Fonction existante | Destination V2 | Statut | Justification |
|---|---|---|---|
| Dashboard SHADOW read-only | `/dashboard`, `/trading`, pages observabilité | Conservée | Les contrats existants restent la source de vérité |
| Systèmes / comptes / PnL | Dashboard + Evaluation | Conservée | Projection backend réutilisée |
| Opportunités / décisions | Trading + Opportunités + Inspector | Remplacée visuellement | Navigation et audit améliorés |
| Ordres / fills / positions | Ordres / Positions / Inspector | Conservée | Aucune logique de position client |
| Backtest CSV / preview | Backtests | Conservée | Même importeur historique |
| Lancement DESIGN/VALIDATION/OOS | Backtests | Conservée | Même `BacktestDashboardService` |
| Progress / Agent traces | Backtest detail / Replay | Enrichie | Réutilise `AgentTraceView` |
| Exports | Backend existant | Conservés | Aucun format Batch 16 supprimé |
| Dashboard HTML/CSS/JS V1 | Routes historiques | Non supprimé dans Batch 22 | Migration non destructive |
| Armement LIVE | Aucun bouton V2 | Non ajouté | Aucune API opérateur sécurisée auditée |

<!-- DOC_REALIGN_FRONTEND_VALIDATION_START -->

## Historique de validation 2026-09-15 — Batch 22.1

Baseline de cette validation historique : `main @ 9f42d3ebc52b71feeedf3b58160187d18bab5a62`.

Validation Frontend exécutée avec pnpm :

```text
pnpm run lint       → OK
pnpm run typecheck  → OK
pnpm run test       → 6 fichiers / 26 tests OK
pnpm run build      → Next.js production build OK
```

Le cockpit expose également les paramètres liés au coût IA/Prompt Cache fournis par le backend. Ces contrôles configurent une policy du AI Gateway ; ils ne déplacent aucune logique de cache fournisseur dans le navigateur.

Le gestionnaire de paquets recommandé dans les commandes de développement Frontend de cette documentation est `pnpm`.

<!-- DOC_REALIGN_FRONTEND_VALIDATION_END -->

<!-- BATCH_24C2_FRONTEND -->
## Addendum Batch 24C.1 / 24C.2 — Decision Intelligence & Trading Chart Analytics Overlays

Le Backtest Cockpit consomme désormais les projections read-only 24C :

```text
/api/frontend/v2/backtests/runs/{campaign_id}/analytics
/api/frontend/v2/backtests/runs/{campaign_id}/analytics/scanner
/api/frontend/v2/backtests/runs/{campaign_id}/analytics/overlays
/api/frontend/v2/backtests/runs/{campaign_id}/opportunities/{opportunity_id}/decision-intelligence
```

Le chart conserve une instance Lightweight Charts et ajoute des couches indépendantes :

- Trading / replay markers ;
- Scanner CandidateOpportunity ;
- décisions et funnel ;
- Risk ;
- Technical Events ;
- structure de marché ;
- ZigZag causal ;
- patterns et segments.

Les couches volumineuses sont désactivées par défaut lorsque leur densité nuirait à la lecture.
`NO_TRIGGER` possède un toggle séparé et n'est jamais massivement rendu par défaut.

Les préférences de visibilité/filtres sont persistées dans Zustand. La sélection d'un objet
Analytics utilise une forme stable préparatoire à 24C.3 :

```text
objectType
objectId
opportunityId
timestamp
label
details
```

Le curseur replay masque toute connaissance future. Les géométries utilisent les timestamps
métier fournis par le backend et ne sont jamais reconstruites depuis les candles.

Compatibilité : une campagne sans Analytics continue d'afficher le replay classique ; la toolbar
Analytics est indisponible/dégradée proprement au lieu de déclencher un recalcul.

Validation locale 2026-09-18 :

```text
npm run lint       → OK
npm run typecheck  → OK
npm run test       → 9 fichiers / 37 tests OK
npm run build      → OK
```

<!-- BATCH_24C3_FRONTEND -->
## Addendum Batch 24C.3 — Decision Intelligence Inspector

Le Historical Replay utilise désormais un Inspector contextuel unique dans le panneau droit. Une sélection chart synchronise `selectedAnalyticsObject` et, lorsqu'il existe, `selectedOpportunityId`, puis ouvre `inspectorOpen`.

L'Inspector affiche les sections Scanner, Agents, Decision Funnel, Risk & Execution et Analytics causal. Il consomme l'endpoint détail 24C.1 existant et n'ajoute aucun endpoint d'écriture.

Sur écran large, le panneau reste intégré au cockpit et redimensionnable horizontalement ; sur viewport plus étroit, la même vue est rendue sous forme de panneau mobile fixe. Le changement de campagne ou de rôle efface la sélection afin d'éviter tout état incohérent.

<!-- BATCH_24C4_FRONTEND -->
## Addendum Batch 24C.4 — Filters & Navigation

Le Historical Replay possède maintenant une couche d'exploration frontend séparée de la visibilité des overlays :

- Scanner : classification, triggers, score min/max ;
- Decision Funnel : Professor FINAL, Palermo, Risk ;
- Analytics : Technical Event family/type/direction et Pattern type/statut causal/direction/pivot source ;
- OR à l'intérieur d'une dimension, AND entre dimensions ;
- chips de filtres actifs, Clear All, compteur, recherche et liste de résultats ;
- Previous/Next sans wrap ;
- sélection hors filtre conservée dans l'Inspector.

La logique de filtering/navigation est centralisée dans `decision-intelligence-navigation.ts`. Le chart, le compteur et le navigator consomment la même liste filtrée.

`OverlaySelection` distingue désormais `timestamp` (géométrie) et `navigationTimestamp` (connaissance causale). Candidate/Scanner utilisent `observed_at`, Technical Events `available_at`, ZigZag `confirmed_at`, Patterns la transition `available_at`, et Funnel `operational_at ?? market_as_of`.

Le store `money-heist-ui-v2` persiste les préférences génériques uniquement. Sa migration v2 accepte les anciens champs 24C.2 `technicalEventFamily` / `technicalEventType`. Les sélections de campagne et la recherche ne sont jamais persistées.

Aucune API n'est ajoutée et aucun calcul Scanner/Analytics/Decision/Risk n'est déplacé dans le navigateur. Voir `archives/batches/24/BATCH_24C4_FILTERS_AND_NAVIGATION.md`.

<!-- DOC_REALIGN_24D4_FRONTEND -->
## Addendum Batch 24D.4 — Research Explorer & Evidence Index

Le Backtest Cockpit expose désormais un Research Explorer observationnel construit uniquement à partir des sidecars 24D pré-calculés.

Endpoints consommés :

```text
GET /api/frontend/v2/backtests/runs/{campaign_id}/research/decision-quality
GET /api/frontend/v2/backtests/runs/{campaign_id}/research/evidence
```

La projection Decision Quality conserve la séparation `DESIGN / VALIDATION / OOS` et présente les rapports descriptifs Scanner Filtering et Funnel Decision Quality. Une cohorte sélectionnée peut ouvrir son Evidence Index paginé, puis synchroniser une preuve avec le replay à son timestamp causal sans changer son identité.

Le frontend ne calcule aucun Forward Outcome, n'infère aucun seuil et ne transforme pas une cohorte descriptive en recommandation. Les sélections Research restent UI-only. Une campagne ancienne dépourvue de sidecars 24D affiche explicitement l'indisponibilité au lieu de lancer un calcul tardif.

Cette couche complète Decision Intelligence 24C mais ne modifie aucune autorité Scanner, Agents, Risk, PAPER ou LIVE.

## Addendum 2026-09-19 — positionnement Spot dans le Backtest Cockpit

Le Backtest Cockpit expose la capacité directionnelle du marché dans les contraintes de campagne. Les presets Spot BTC/USDC et les contraintes publiques Kraken utilisent `SPOT_LONG_ONLY` par défaut. L’opérateur voit explicitement `SPOT · LONG ONLY` dans la configuration et la revue finale. `LONG_SHORT` reste sélectionnable uniquement pour une expérience dont le marché sous-jacent le permet réellement.

Le frontend ne filtre aucun trade après coup : il transmet la capability au backend, qui reste l’autorité sur Professor/Risk/PAPER.

<!-- DECISION_CHART_V1 -->
## Decision Chart — replay au timeframe de décision

L’analyse avancée des backtests utilise désormais une projection `money-heist.frontend-decision-chart.v1` :

- les bougies affichées sont celles du `decision_timeframe` réellement lié au run (`1h` pour le runtime MTF issu de `1m` / `5m` / `15m`, sinon le timeframe source) ;
- les indicateurs sont reconstruits côté backend avec le `FeatureEngine` canonique à partir du dataset immuable, puis chaque timestamp Scanner doit retrouver le `FeatureSnapshot.snapshot_id` persisté ; en cas d’écart la projection échoue fermée ;
- les entrées Scanner visibles couvrent notamment RSI 14, ADX 14, spread EMA 12/26, expansion ATR, ratio de volume et distances au range 20 ; EMA 12/26 et bornes du range 20 sont superposées au prix ;
- le graphe de replay avancé charge toute la série du rôle sélectionné au `decision_timeframe` ; le curseur de replay sert à inspecter un instant sans tronquer les bougies, les courbes d’indicateurs ni les marqueurs déjà persistés ;
- il n’affiche plus les labels texte, événements PAPER, pivots ou patterns : seuls les marqueurs `Professor FINAL` sont rendus ;
- le clic sur un marqueur sélectionne l’opportunité canonique et réutilise `DecisionIntelligenceInspector` pour expliquer Scanner, spécialistes, Professor, Risk et PAPER ;
- cette projection reste strictement observationnelle et ne recalcule aucune décision ni aucun ordre.


<!-- DECISION_CHART_TERMINAL_PRO_20260920 -->

## Addendum 2026-09-20 — Decision Chart, Terminal Pro et Trade Story

L'Analyse avancée du Backtest Cockpit possède désormais un Decision Chart spécialisé. Il ne remplace pas les artefacts backend : il les projette dans une narration transactionnelle.

### Sources affichées

```text
dataset immuable
→ candles resamplées au decision_timeframe
→ Feature Engine canonique pour les indicateurs du chart
→ Professor FINAL pour LONG / SHORT / NO_TRADE
→ Funnel / Risk pour les rejets déterministes
→ replay.trades pour les closed trades PAPER
→ Decision Intelligence / TradeProposal pour stop, targets et contexte
```

La projection fail-closed vérifie l'identité des snapshots Scanner disponibles avant d'accepter une reconstruction d'indicateurs. Aucun Forward Outcome n'est utilisé comme trade hypothétique.

### Sémantique visuelle

- `LONG` / `SHORT` : décision Professor FINAL ;
- croix Risk : proposition rejetée déterministiquement ;
- entrée/sortie reliées : trade PAPER réellement exécuté et fermé ;
- `NO_TRADE` : décision valide sans exécution ;
- SL/TP : niveaux de la TradeProposal du trade sélectionné uniquement ;
- `CLOSED` : sortie réelle lorsque la cause STOP/TARGET n'est pas persistée dans le contrat disponible.

Trois modes de lecture sont proposés : `Mixte`, `Trades` et `Décisions`. Le trade sélectionné est renforcé, mais les autres markers conservent leur couleur et une visibilité suffisante ; le focus ne devient pas un mode solo implicite.

### Résultat du trade

Pour un closed trade PAPER associé sans ambiguïté :

```text
rendement net % = net_pnl / (abs(quantity) × entry_price) × 100
```

L'UI distingue `WIN`, `LOSS` et `FLAT`. Une valeur manquante, un NO_TRADE, un rejet Risk, un trade ouvert ou un matching ambigu n'est jamais transformé en faux `FLAT`.

Le PnL brut d'exécution affichable à partir du contrat ReplayTrade est dérivé de `net_pnl + fees`. Le slippage est présenté séparément lorsqu'il est disponible.

### Trade Story Inspector

L'en-tête de l'Inspector privilégie la lecture opérateur : direction, confiance Professor, statut Risk, rendement net, durée et R réalisé lorsque le stop planifié permet ce calcul.

La section Trade Story synthétise :

```text
Professor
→ Risk
→ Entry
→ Exit
```

Puis compare `Entry prévu / Entry réel`, stop, targets, exit réel et RR attendu. Le bloc `Pourquoi ce résultat ?` expose mouvement brut, PnL brut d'exécution, frais/slippage et PnL net.

Les détails Agents, Palermo, Funnel et Analytics restent accessibles mais ne dominent plus la première lecture.

### Navigation et contexte

Le cockpit expose un résumé de session et des actions trade précédent/suivant. La sélection reste UI-only et ne modifie jamais les artefacts de campagne.

Le focus visuel respecte la règle suivante : **accentuer le trade choisi sans effacer les autres décisions**. Les markers non sélectionnés restent pleinement identifiables, tandis que les lignes et endpoints secondaires sont seulement modérément atténués.

### Validation locale ciblée

Validation fournie le 2026-09-20 après consolidation Trade Story et rééquilibrage du focus :

```text
pnpm typecheck → OK
Vitest ciblé   → 5 fichiers / 20 tests OK
git diff --check → aucune erreur whitespace ; warnings LF→CRLF Windows uniquement
```

Cette validation ciblée ne remplace pas la suite frontend/backend complète à exécuter avant intégration.
