# Money Heist — État actuel post-Batch 17b

**Statut :** Référence d’alignement active  
**Date :** 2026-09-09  
**Nom de fichier conservé :** `00_ETAT_ACTUEL_POST_BATCH_15.md` pour continuité des références existantes  
**Baseline d’entrée de la finalisation :** `8db98a4` — `feat(backtest): add evaluation ai modes and reproducibility`

---

## 1. Rôle de ce document

Ce document décrit l’état intégré du projet après la finalisation du **Batch 16 — Backtesting & Historical Replay**.

En cas de contradiction avec une formulation historique des documents `01_...` à `08_...`, les références suivantes prévalent pour l’état courant :

1. le code intégré sur GitHub `main` ;
2. ce document ;
3. `09_ROADMAP_DEVELOPPEMENT.md` ;
4. `10_DECISIONS_ET_CHANGELOG.md` ;
5. `11_BACKTESTING_ET_REPLAY_HISTORIQUE.md` pour le contrat détaillé du Batch 16.

Les documents initiaux restent des références de domaine lorsque leurs principes n’ont pas été explicitement remplacés.

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
16 — Backtesting & Historical Replay
```

Le Batch 16 ajoute un banc d’essai historique end-to-end mais **n’arme pas le LIVE** et ne constitue pas, à lui seul, une autorisation de premier ordre réel.

---

## 3. Pipeline historique disponible

Le chemin historique réutilise les composants de production au lieu de dupliquer la logique métier :

```text
Dataset OHLCV historique immuable
→ ReplayClock
→ Feature Engine
→ DeterministicScanner
→ CandidateOpportunity
→ Compute Gate / Orchestration agents
→ TradeProposal
→ Risk Engine déterministe
→ PaperTradingPipeline
→ PaperBroker
→ cycle de vie historique des positions
→ PortfolioRiskState dynamique
→ equity curve
→ Batch 10 Evaluation
```

Les invariants principaux sont :
- aucune bougie future visible à l’étape courante ;
- une décision prise à la clôture N ne peut pas utiliser le high/low de N pour gérer la position nouvellement ouverte ;
- Risk Engine identique au chemin PAPER ;
- exécution historique exclusivement via PaperBroker ;
- frais et slippage explicites ;
- stop prioritaire si stop et target sont touchés dans une même bougie sans ordre intrabar observable ;
- gap défavorable au stop exécuté depuis l’open puis slippage PAPER ;
- gap favorable au target plafonné au target ;
- target V1 : premier target atteint, fermeture complète ;
- aucune dépendance du package backtest vers l’exécution LIVE.

---

## 4. Données et reproductibilité

Chaque dataset historique est identifié par contenu avec :
- symbole ;
- timeframe ;
- source ;
- période ;
- nombre de bougies ;
- hash SHA-256 ;
- identifiant/version stables ;
- métadonnées explicites.

Chaque `BacktestRun` référence notamment :
- dataset/version ;
- période ;
- système ;
- version Risk ;
- version Feature Engine ;
- version Scanner ;
- versions de prompts ;
- versions de modèles ;
- mode IA ;
- version du code ;
- version du modèle d’exécution historique ;
- seed ;
- frais/slippage ;
- politique intrabar ;
- hypothèses d’exécution additionnelles.

Un fingerprint business permet de comparer deux runs sans dépendre d’identifiants techniques volatils qui ne changent pas le résultat économique.

---

## 5. Modes IA du backtest

Trois modes sont séparés :

### MOCK
Client IA déterministe de test. Aucun fournisseur réel requis.

### CACHED
Réponses provenant exclusivement d’un cache déterministe. Un cache miss échoue sans appel upstream.

### LIVE_EVAL
Le vrai AI Gateway peut appeler un fournisseur réel et appliquer ses budgets, mais **l’exécution de trading reste PAPER uniquement**.

`LIVE_EVAL` signifie « IA réelle pour évaluation historique » et ne signifie jamais « ordre LIVE ».

---

## 6. Evaluation et rapports

Le Batch 16 alimente le Batch 10 Evaluation avec :
- ordres/fills PAPER ;
- frais ;
- slippage ;
- PnL réalisé/non réalisé ;
- equity curve ;
- win rate ;
- expectancy ;
- profit factor ;
- drawdown ;
- exposition ;
- coûts IA ;
- métriques agents ;
- Economic Net ;
- Self-Funding Ratio.

MAE/MFE restent optionnels lorsqu’ils ne sont pas reconstructibles de manière fiable à partir du niveau de granularité historique disponible. Ils ne doivent pas être inventés.

---

## 7. DESIGN, VALIDATION et OOS

Le Batch 16 fournit des périodes explicitement typées :

```text
DESIGN
→ VALIDATION
→ OOS
```

Elles sont non chevauchantes et restent à l’intérieur des bornes du dataset.

Les métriques OOS sont conservées séparément. Elles ne doivent pas être fusionnées avec DESIGN/VALIDATION pour masquer une dégradation hors échantillon.

Le « test final » OOS ne doit pas être réutilisé indéfiniment pour ajuster les paramètres.

---

## 8. Walk-forward V1

Le walk-forward V1 construit des fenêtres roulantes :

```text
DESIGN window
→ VALIDATION window
→ OOS window
→ roll
```

V1 n’intègre **aucun optimiseur automatique**. Une même `BacktestConfig` figée est utilisée pour les trois périodes d’une fenêtre et pour les fenêtres générées par un plan donné.

Toute future optimisation devra être un composant séparé, explicitement versionné et soumis à des protections contre l’overfitting/data snooping.

---

## 9. Exports

Les exports déterministes incluent :
- manifeste de run JSON canonique ;
- fingerprint business ;
- rapport DESIGN/VALIDATION/OOS JSON ;
- rapport walk-forward JSON ;
- equity curve CSV ;
- closed trades CSV ;
- exports Batch 10 existants.

---

## 10. Sécurité LIVE

Le Batch 16 n’ajoute aucun chemin vers :
- `app.trading.live` ;
- `KrakenSpotLiveBroker` ;
- `ControlledLiveExecutionService` ;
- API privée d’ordre LIVE.

Des tests de frontière inspectent le package backtest pour préserver cette isolation.

Le mécanisme Batch 15 reste fail-closed :

```text
LIVE_DISABLED
→ LIVE_PREFLIGHT
→ LIVE_ARMED
```

La présence de credentials ne suffit jamais à armer le LIVE.

---

## 11. Gate avant premier ordre réel

La disponibilité du moteur historique ne signifie pas que la validation historique est automatiquement réussie.

La gate opérationnelle reste :

```text
Datasets historiques sélectionnés et contrôlés
→ Backtests DESIGN
→ Validation
→ OOS
→ Walk-forward
→ analyse des métriques / coûts / drawdown
→ PAPER / SHADOW suffisamment observé
→ profil Balanced numérique validé
→ timeframes et freshness validés
→ Preflight LIVE
→ décision opérateur explicite
→ petit capital réel
```

Les seuils numériques de promotion doivent être définis avant de juger le test correspondant afin de limiter le cherry-picking.

---

## 12. Bloqueurs LIVE encore ouverts

Même après Batch 16, restent notamment à décider/valider avant un premier ordre réel :
- profil Balanced numérique complet ;
- timeframes de production ;
- seuils de fraîcheur Market Data ;
- datasets historiques retenus pour la gate ;
- critères quantitatifs d’acceptation OOS/walk-forward ;
- durée/volume minimal d’observation PAPER/SHADOW ;
- environnement 24/7.

Aucune valeur ne doit être inventée pour fermer artificiellement ces points.

---

## 13. Roadmap active

```text
Batch 16 — Backtesting & Historical Replay — livré
Batch 17 — Rio / Denver avancés — livré
Batch 18 — Réputation et ablation
Batch 19 — Recruitment Engine
Batch 20 — Task Force Agents
Batch 21 — Master Portfolio Layer
```

Denver avancé peut consommer les statistiques Batch 16 et Rio peut consommer les analytics publics Kraken Futures en PAPER/SHADOW.

---

## 14. Prochaine étape

1. intégrer et valider le lot final Batch 16 ;
2. exécuter des campagnes historiques réelles avec datasets/version/config figés ;
3. définir avant test les critères de passage OOS/walk-forward ;
4. poursuivre PAPER/SHADOW avec LIVE non armé ;
5. préparer Batch 18 (réputation/ablation) sans interpréter Batch 17 comme une autorisation LIVE.

---

## 15. Extension Batch 16.7 — interface opérateur de backtest

Le moteur Batch 16 est désormais exposé par `/dashboard/backtest` pour lancer des campagnes historiques sans ligne de commande. L'interface couvre import CSV, configuration PAPER/Risk/IA, DESIGN/VALIDATION/OOS, walk-forward optionnel, résultats et exports.

Cette extension ne change pas la gate LIVE : elle facilite l'exécution des preuves historiques mais ne transforme aucun résultat en autorisation automatique. `LIVE_EVAL` reste IA réelle + trading PAPER.



## 16. Addendum Batch 17a — Denver avancé et infrastructure Rio/Denver

Le Batch 17a ajoute l’infrastructure commune des spécialistes avancés sans modifier les frontières
Risk/PAPER/LIVE.

État implémenté :
- Rio et Denver disposent de schémas stricts, prompts versionnés et entrées registry `ON_DEMAND` ;
- aucun des deux agents ne possède d’outil, secret, accès broker, accès Risk Engine ou capacité LIVE ;
- l’orchestration expose un spécialiste avancé uniquement lorsqu’un contexte typé et utilisable est
  fourni ;
- Rio reste indisponible en pratique tant qu’aucune vraie source dérivés fiable n’est injectée ;
- Denver peut recevoir un `DenverContext` construit par code déterministe depuis les statistiques
  historiques Batch 16 ;
- les statistiques Denver sont content-addressed, `as_of`, liées aux runs/datasets sources et
  filtrées sur les trades fermés avant le timestamp courant ;
- un même setup ne peut pas être alimenté par des configurations de stratégie incompatibles ou par
  plusieurs reruns comptant deux fois la même opportunité ;
- le MOCK avancé conserve les réponses historiques lorsque Rio/Denver ne sont pas disponibles et
  n’ajoute Denver au plan que lorsqu’un contexte Denver existe.

Le Batch 17a ne fournit pas de source réelle funding/OI/liquidations. Cette activation appartient au
Batch 17b. Il ne ferme pas non plus les bloqueurs LIVE `OPEN-006` et `OPEN-007`.

## 17. Addendum Batch 17b — Rio réel sur Kraken Futures Analytics

Le Batch 17b active Rio avec une source dérivés réelle et publique, tout en conservant le premier
LIVE en Kraken Spot/EUR.

État implémenté :
- adaptateur public `KrakenFuturesAnalyticsProvider`, sans authentification ni méthode d'ordre ;
- mapping initial `BTC/EUR → PF_XBTUSD`, `ETH/EUR → PF_ETHUSD`, `SOL/EUR → PF_SOLUSD` ;
- funding, open interest, variation d'open interest et long/short ratio normalisés ;
- séparation long/short des liquidations laissée absente lorsque la source publique ne la garantit
  pas ;
- refresh dérivés déclenché seulement après détection d'une opportunité par le Scanner ;
- sidecar non critique : une panne analytics ne bloque pas le Market Data spot ni le chemin PAPER ;
- cache Rio borné par âge et cooldown ; cache stale => Rio indisponible ;
- `KrakenFuturesRioContextProvider` utilisé à la fois comme refresher asynchrone et provider de
  contexte synchrone pour l'orchestration ;
- composition Rio + Denver possible via `CompositeSpecialistContextProvider` ;
- diagnostics read-only `REFRESHED / CACHE_HIT / DEGRADED / STALE / UNAVAILABLE` ;
- smoke réseau public Kraken Futures validé sans clé API.

Rio reste un spécialiste consultatif. Il ne possède ni broker, ni Risk Engine, ni credentials, ni
capacité d'activation LIVE. Les données analytics courantes ne sont pas utilisées rétroactivement en
backtest historique : un futur replay Rio exigera un dataset dérivés historique horodaté et
reproductible.
