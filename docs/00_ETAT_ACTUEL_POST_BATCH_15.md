# Money Heist — État actuel post-Batch 23A.4

**Statut :** référence d’alignement active  
**Date :** 2026-09-16
**Nom de fichier conservé :** `00_ETAT_ACTUEL_POST_BATCH_15.md` pour continuité des références existantes
**Baseline fonctionnelle consolidée :** `611bef38f9e056ea7d7964a0f10191bac58551e4` (`main`)
**Clôture documentaire précédente :** `096f5e5f4c16b47f5e9926065c3c4206dfc19c17` — Batch 23A.1

---

## 1. État intégré

Money Heist dispose aujourd’hui d’un pipeline déterministe/agentique complet pour PAPER, SHADOW et Historical Replay, d’un chemin LIVE protégé mais non promu automatiquement, d’une couche portefeuille maître, et d’un Frontend V2 Next.js.

Chaîne de décision principale :

```text
Market Data
→ Feature Engine
→ Scanner
→ Compute Gate
→ Professor PLAN
→ spécialistes indépendants
→ Palermo
→ Professor FINAL
→ TradeProposal éventuel
→ Risk Engine déterministe
→ PAPER / SHADOW / LIVE selon autorisation opérateur
→ Evaluation / Lisbon
```

Le Risk Engine reste l’autorité de risque. Aucun LLM, frontend, cache, Recruitment Engine, Task Force ou Master Professor ne peut contourner cette frontière.

## 2. Historical Replay / Backtest

Le Batch 16 est techniquement opérationnel et PAPER-only. Le smoke LIVE_EVAL de référence reste :

- commit technique : `294cfa2547f94c9694fdc65758c3f9435ff55dd2` ;
- campagne : `177add07-b684-440c-b8ca-a37313a6eac5` ;
- dataset : `BTC/USDC:1h:4f5515aef296533f` ;
- progression : `345/345` ;
- 15 opportunités ;
- 14 `NO_TRADE`, 1 `SHORT` ;
- Risk Engine : `RESIZED` ;
- 1 ordre PAPER ;
- 0 échec technique observé sur ce smoke.

Cette preuve est technique, pas une preuve de rentabilité ni une autorisation LIVE. DESIGN / VALIDATION / OOS, walk-forward, multi-régimes et PAPER/SHADOW restent nécessaires avant promotion de capital réel.

## 3. Agents, Recruitment et Task Force

Le registre opérationnel conserve Professor, Palermo, Lisbon, Berlin, Tokyo, Nairobi, Rio et Denver. Les versions de prompts intégrées après optimisation Prompt Cache sont notamment Professor `v6` et spécialistes `v5`.

Recruitment reste advisory-only et opérateur-gaté. Les Task Forces restent temporaires, registry-only, provenance-preserving et sans autorité Risk/LIVE.

## 4. Master Portfolio Layer

Le code intégré contient la couche `app/portfolio` : allocation, preuves, advisory Master Professor en SHADOW, revue opérateur, candidats de changement de policy et clôtures/audits. Cette couche reste opérateur-gatée et ne transforme pas une recommandation analytique en autorité de risque ou en ordre LIVE.

## 5. Frontend V2 — Batch 22 / 22.1

Le cockpit est une application Next.js/React/TypeScript sous `frontend/`. FastAPI reste la source de vérité métier.

Le Backtest Cockpit expose :

```text
Dataset → Périodes → Risk → IA → Exécution → Données avancées → Walk-Forward → Revue
```

Le sidecar `.money-heist/frontend-v2/` persiste les datasets, configurations, progression/traces, résumés et exports nécessaires au replay durable. Le navigateur ne recalcule ni Scanner, ni décision agentique, ni Risk Engine.

Validation Frontend de référence du 2026-09-15 : lint, typecheck, 26 tests Vitest et build Next.js réussis.

## 6. OpenAI Prompt Cache

Money Heist utilise un transport versionné `money-heist.prompt-transport.v2` permettant un Prompt Cache OpenAI explicite lorsque la route déclare la capacité correspondante.

Le préfixe `developer` stable contient rôle/instructions/version de prompt et fingerprint de schéma. Les données dynamiques du run restent après le breakpoint. La policy est désactivée par défaut et ne change aucune autorité métier.

La comptabilité distingue :

- input normal ;
- cache read ;
- cache write ;
- output ;
- coût réel ;
- coût contrefactuel sans cache ;
- économie nette estimée.

Le Prompt Cache OpenAI est distinct du cache de réponses Historical Replay `money-heist.backtest-ai-cache.v2`.

## 7. Market Data et utilitaires historiques

Les utilitaires de données ont été regroupés sous `scripts/market_data/` :

- `audit_kraken_derivatives_coverage.py` ;
- `download_binance_history.py` ;
- `probe_kraken_derivatives_history.py` ;
- `sync_binance_btc_usdc_h1.py` ;
- `sync_binance_btc_usdc_h1_v2.py`.

Ils servent à auditer/télécharger/préparer les datasets historiques. Ils ne constituent pas une nouvelle autorité d’exécution.

## 8. Nettoyage du dépôt

Les artefacts historiques de livraison Batch devenus obsolètes ont été retirés après audit de références et validation complète des tests. Les commits de nettoyage de référence sont :

- `c4ffda0` — retrait d’artefacts de livraison Batch obsolètes ;
- `9f42d3e` — retrait d’artefacts historiques de clôture.

Le dépôt de travail était propre et `HEAD == origin/main` sur `9f42d3e` après cette opération.

## 9. Gates LIVE toujours applicables

Le LIVE n’est jamais déduit d’un backtest ou d’un résultat IA. Avant capital réel, il faut au minimum :

```text
Backtests reproductibles multi-régimes
+ OOS
+ walk-forward
+ PAPER/SHADOW
+ paramètres Risk explicitement validés
+ Market Data production validé
+ préflight sécurité
+ décision opérateur
```

Les timeframes de production et les limites numériques Balanced restent des décisions à valider explicitement avant un premier ordre réel.

## 10. Documentation de référence

Ordre recommandé :

1. `00_ETAT_ACTUEL_POST_BATCH_15.md` ;
2. `docs/01_PROJECT_MASTER.md` ;
3. `docs/02_ARCHITECTURE.md` ;
4. `03_SYSTEME_AGENTS.md` ;
5. `05_MARKET_DATA_ET_EXECUTION.md` ;
6. `06_EVALUATION_ET_APPRENTISSAGE.md` ;
7. `08_API_ET_MODELES_DE_DONNEES.md` ;
8. `09_ROADMAP_DEVELOPPEMENT.md` ;
9. `10_DECISIONS_ET_CHANGELOG.md` ;
10. `11_BACKTESTING_ET_REPLAY_HISTORIQUE.md` ;
11. `12_FRONTEND_ET_INTERFACE.md` ;
12. `docs/ADR_031_OPENAI_PROMPT_CACHE_ET_COUTS.md`.

GitHub `main` reste la référence intégrée lorsqu’une formulation historique subsiste dans un addendum ancien.

<!-- BATCH23A1_STATE_CLOSURE -->
## 11. Batch 23A.1 — Decision Funnel Baseline

Batch 23A.1 est livré sur `main` au commit `fbec1d3fadaf811c6e84d33741aa08166cc472cd`.

La couche `DecisionFunnelReport` mesure le chemin Historical Replay sans modifier son comportement :

```text
candles
→ Scanner
→ CandidateOpportunity
→ Compute Gate
→ orchestration IA
→ Professor FINAL
→ TradeProposal
→ Risk Engine
→ ordre/fill PAPER
```

Deux compteurs techniques pré-Scanner sont conservés : warm-up incomplet et clôture hors timeframe de décision. Le rapport agrège ensuite triggers Scanner, opportunités, gates IA, décisions Professor, Risk et exécution.

Invariants documentés :
- `candles_evaluated = pre_scanner_skips + scanner_evaluations` ;
- `scanner_evaluations = scanner_no_trigger + scanner_triggered` ;
- aucun seuil Scanner/Professor/Risk n'est modifié ;
- le rapport n'entre jamais dans `DecisionContext` ;
- les données postérieures à la décision, notamment `closed_trades`, restent dans `post_hoc` ;
- le fingerprint business historique reste indépendant des nouveaux compteurs d'observation.

Exports de campagne :
- `design-decision-funnel.json` ;
- `validation-decision-funnel.json` ;
- `oos-decision-funnel.json`.

---

<!-- BATCH23A2_4_STATE_CLOSURE -->
## 12. Batch 23A.2 à 23A.4 — clôture consolidée

La pile de mesure causale 23A est désormais livrée sur `main` :

- `b78266efe5c0bf203d75348907cac5000472e9c6` — Batch 23A.2 Forward Outcomes ;
- `42903cce9e694fdf1f23923fdba0708176e7775a` — Batch 23A.3 Funnel Outcome Attribution ;
- `611bef38f9e056ea7d7964a0f10191bac58551e4` — Batch 23A.4 Scanner Forward Outcomes.

Elle couvre maintenant :

```text
bougies évaluables
→ Scanner evaluation
   ├─ NO_TRIGGER
   ├─ TRIGGER_BELOW_CANDIDATE_THRESHOLD
   └─ CANDIDATE_OPPORTUNITY
        → Compute Gate
        → Professor / spécialistes / Palermo
        → TradeProposal éventuel
        → Risk
        → PAPER execution
```

et mesure post-hoc les horizons H1/H3/H5/H10/H20 sans rendre ces données visibles au pipeline décisionnel de l'opportunité évaluée.

Garanties consolidées :
- aucun changement de seuil Scanner, prompt Professor, règle Risk ou règle d'exécution ;
- Forward Outcomes calculés dans le timeframe de décision ;
- frontières DESIGN / VALIDATION / OOS strictes ;
- horizons incomplets sans publication de métriques de prix partielles ;
- attribution 23A.3 descriptive uniquement, sans classement automatique ni autorité de tuning ;
- 23A.4 réutilise les `ScanResult` déjà émis et ne rappelle jamais le Scanner ;
- `BacktestConfig`, `run_id` et fingerprint business historique restent inchangés.

Exports additionnels par période :
- `*-forward-outcomes.json` ;
- `*-funnel-outcome-attribution.json` ;
- `*-scanner-forward-outcomes.json`.

## 13. Prochaine phase

La prochaine phase utile est une **campagne historique longue multi-régimes** exploitant ensemble Decision Funnel, Candidate Forward Outcomes, Funnel Outcome Attribution et Scanner Forward Outcomes. Les résultats doivent être analysés sur DESIGN / VALIDATION / OOS avant toute proposition de modification de seuil.

La parité LIVE ↔ Historical Replay, PAPER/SHADOW prolongé et les gates opérateur restent ensuite nécessaires avant toute promotion LIVE.
<!-- BATCH24A1_STATE -->
## Batch 24A.1 — Analytics Lab Foundation

L'Analytics Lab possède désormais une fondation observation-only distincte du
`BacktestRun` : contrats immuables, provenance dataset/as-of/MTF, versions de
composants, snapshots vides autorisés, manifeste et fingerprints déterministes.
Aucun élément Analytics n'est injecté dans Scanner, `CandidateOpportunity`,
`DecisionContextV1`, agents, Risk, PAPER ou LIVE. Les Forward Outcomes Batch 23A
restent la vérité post-hoc canonique.
