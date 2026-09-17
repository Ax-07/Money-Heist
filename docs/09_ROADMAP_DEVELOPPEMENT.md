# Money Heist — Roadmap de Développement

**Document :** Plan de développement par lots
**Version :** 0.7
**Statut :** Roadmap active — alignée post-Batch 23A.4

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

**État : livré ; smoke LIVE_EVAL end-to-end validé le 2026-09-11. Validation statistique étendue encore requise avant LIVE.**

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
Le smoke technique LIVE_EVAL est validé sur le commit
`294cfa2547f94c9694fdc65758c3f9435ff55dd2`, campagne
`177add07-b684-440c-b8ca-a37313a6eac5`, dataset
`BTC/USDC:1h:4f5515aef296533f` : `345/345`, 15 opportunités,
14 `NO_TRADE`, 1 `SHORT`, 1 décision Risk `RESIZED`, 1 ordre PAPER et 0 échec technique.

Cette validation prouve que le pipeline réel IA → proposition → Risk déterministe → PAPER peut
fonctionner de bout en bout. Elle **ne valide pas encore la gate statistique ou la promotion LIVE**.
Les datasets multi-régimes, critères d’acceptation DESIGN/VALIDATION/OOS, walk-forward et campagnes
PAPER/SHADOW doivent encore être exécutés et évalués avant un premier ordre réel.

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

Selon disponibilité des données :
- dérivés ;
- statistiques historiques issues du moteur Batch 16 ;
- setup DB ;
- outils statistiques réels pour Denver.

Denver ne doit pas inventer des probabilités ou statistiques absentes.

---

## 21. Batch 18 — Réputation et ablation

- réputation multidimensionnelle ;
- tests d’ablation sur datasets/runs comparables ;
- états ON_DEMAND/SHADOW/PROBATION ;
- analyses marginales.

---

## 22. Batch 19 — Recruitment Engine

**État : livré et validé jusqu'au Batch 19e.1 ; documentation réalignée au Batch 19e.2.**

Livré :
- contrats `RecruitmentProposal` / `RecruitmentCandidateSpec` ;
- lifecycle candidat séparé de `AgentState` ;
- gates population, fréquence et compute candidat ;
- campagnes twins `BASELINE` / `WITH_CANDIDATE` sur Historical Replay/PAPER ;
- comparabilité, provenance et gate OOS ;
- bridge vers l'ablation et la réputation Batch 18 ;
- coûts candidat directs et coût marginal système distincts ;
- paquet d'évidence auditable et reproductible ;
- avis `REJECT / EXTEND / PROBATION / RECOMMEND_PROMOTION` ;
- planning de transition opérateur-gaté ;
- audit `FRESH / STALE` et stale-plan guards ;
- exports publics `app.recruitment` ;
- endpoint GET read-only `/api/recruitment/capabilities`.

Non livré volontairement :
- mutation automatique d'`AgentRegistry` ;
- promotion automatique ACTIVE/ON_DEMAND ;
- autorité LIVE candidat ;
- endpoint HTTP d'écriture Recruitment.

---

## 23. Batch 20 — Task Force dynamique

**État : livré et validé.**

Livré :
- contrats temporaires, expiration et mission ;
- lifecycle opérateur-gaté ;
- policies population, budget, appels, retries et tools ;
- composition registry-only par rôle/capability ;
- réputation multidimensionnelle Batch 18 ;
- provenance, fingerprints et stale detection ;
- exécution multi-membres via AI Gateway ;
- agrégation provenance-preserving et Red Team optionnel ;
- trigger bridge explicite ;
- `TaskForceReport` grounded dans le Professor final ;
- Evaluation coût/latence et economic lift conditionnel ;
- Historical Replay PAPER baseline vs treatment ;
- seal de reproductibilité et audit `FRESH / STALE` ;
- exports publics consolidés.

Non livré volontairement :
- création/promotion automatique d’agents ;
- mutation automatique d’`AgentRegistry` ;
- score magique de consensus/réputation ;
- autorité Risk ou LIVE ;
- ordre ou `TradeProposal` direct depuis la Task Force.

---

## 24. Batch 21 — Master Portfolio Layer

**État intégré : couche fonctionnelle présente dans `app/portfolio`.**

Fonctions observées dans l’état courant :
- enveloppes/allocation multi-crews ;
- analyse de preuves d’allocation ;
- Master Professor en mode SHADOW/advisory ;
- revue opérateur et clôture auditable ;
- candidats de changement/remplacement de policy ;
- fingerprints, seals et guards de fraîcheur.

Frontières : aucune recommandation Master Professor ne remplace le Master Risk/Risk Engine, n’applique silencieusement une policy ou n’accorde une autorité LIVE.

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

État de construction : Batch 23A.1 Decision Funnel Baseline livré sur `main` au commit `fbec1d3fadaf811c6e84d33741aa08166cc472cd`. Le pipeline est désormais instrumenté pour expliquer quantitativement où les opportunités sont filtrées sans modifier le comportement de trading.

Priorités suivantes :

1. livrer Batch 23A.2 — Forward Outcomes post-hoc pour chaque `CandidateOpportunity`, sans feedback dans `DecisionContext` ;
2. exécuter des campagnes historiques longues et multi-régimes avec DESIGN / VALIDATION / OOS et walk-forward en exploitant le Decision Funnel ;
3. mesurer la fréquence de trade, les pertes de funnel, la qualité des opportunités, les coûts IA et l’apport marginal des agents avant tout assouplissement de seuil ;
4. poursuivre la parité du contexte décisionnel LIVE ↔ Historical Replay ;
5. valider explicitement timeframes de production et limites numériques Balanced ;
6. maintenir le LIVE non promu tant que PAPER/SHADOW, sécurité et preflight ne sont pas satisfaits.

<!-- BATCH22_FRONTEND_V2 -->
## Batch 22 — Frontend V2 / Trading Cockpit

**État du lot :** livré comme overlay d'intégration sur la baseline `34351184f193e658a375667bdf19594d2defb3ec`.

Objectif : remplacer progressivement l'expérience Dashboard V1 par un cockpit Next.js unifié LIVE/PAPER/SHADOW/BACKTEST sans déplacer l'autorité métier dans le navigateur.

Livré : foundation Next.js/TypeScript strict, navigation desktop/mobile, Trading Workspace, chart via adapter Lightweight Charts, Backtests DESIGN/VALIDATION/OOS, Historical Replay, Decision Trace, vues Opportunités/Ordres/Positions/Historique/Agents/Evaluation, Settings read-only lorsque le backend n'expose pas d'écriture, API V2 minimale et documentation `12_FRONTEND_ET_INTERFACE.md`.

Le Dashboard V1 n'est pas supprimé dans ce batch. La migration est volontairement non destructive.

<!-- BATCH22_1_BACKTEST_COCKPIT -->
## Batch 22.1 — Frontend V2 Backtest Cockpit Completion

Le lanceur suit Dataset → Périodes → Risk → IA → Exécution → Données avancées → Walk-Forward → Revue. Les defaults deviennent visibles/modifiables et les datasets/artefacts de replay V2 sont persistés localement.

<!-- DOC_REALIGN_POST_BATCH22_ROADMAP_START -->

## État documentaire au 2026-09-15

Batch 22 / 22.1 est livré. Le Prompt Cache OpenAI a été intégré ensuite dans le AI Gateway et le dépôt a été nettoyé des anciens artefacts de livraison Batch. La roadmap historique est conservée pour traçabilité ; la section « Prochaine action » ci-dessus porte l’orientation courante.

<!-- DOC_REALIGN_POST_BATCH22_ROADMAP_END -->

<!-- BATCH23A1_ROADMAP -->
## Batch 23A.1 — Decision Funnel Baseline

**État : livré et validé le 2026-09-16.**
**Commit de référence :** `fbec1d3fadaf811c6e84d33741aa08166cc472cd`.

Livré :
- instrumentation Historical Replay strictement observationnelle ;
- compteurs pré-Scanner warm-up / clôtures hors timeframe de décision ;
- funnel Scanner → CandidateOpportunity → Compute Gate → IA → Professor → TradeProposal → Risk → ordre/fill ;
- reason codes agrégés ;
- invariants de conservation ;
- exposition additive dans `PeriodSummary` ;
- exports JSON par période ;
- tests de non-régression/reproductibilité ;
- aucune modification de seuil Scanner/Professor/Risk ou règle d'exécution.

### Batch 23A.2 — Forward Outcomes

**État : livré et validé le 2026-09-16 — `b78266efe5c0bf203d75348907cac5000472e9c6`.**

- H1/H3/H5/H10/H20 dans le timeframe de décision ;
- rendement close-to-close, max-upside, max-downside et first-hit ;
- gaps / frontières de période explicites ;
- aucune métrique de prix partielle pour horizon incomplet ;
- aucune donnée future dans `DecisionContext`.

### Batch 23A.3 — Funnel Outcome Attribution

**État : livré et validé le 2026-09-16 — `42903cce9e694fdf1f23923fdba0708176e7775a`.**

- croisement candidat ↔ métadonnées du pipeline ↔ Forward Outcomes ;
- agrégations par statut terminal, régime, triggers, Compute Gate, Professor, Risk et échecs ;
- métriques brutes et directionnelles lorsque LONG/SHORT existe ;
- dimensions multi-valuées explicitement non exclusives ;
- analyse descriptive uniquement, sans classement ou tuning automatique.

### Batch 23A.4 — Scanner Forward Outcomes

**État : livré et validé le 2026-09-16 — `611bef38f9e056ea7d7964a0f10191bac58551e4`.**

- outcome post-hoc pour chaque évaluation Scanner ;
- couverture `NO_TRIGGER`, `TRIGGER_BELOW_CANDIDATE_THRESHOLD`, `CANDIDATE_OPPORTUNITY` ;
- score exact, seuil réellement utilisé et marge au seuil ;
- agrégations par classification, score exact, trigger et régime ;
- conservation stricte avec le Decision Funnel ;
- aucun rerun ni changement du Scanner.

### Phase suivante — exploitation empirique

Exécuter des campagnes longues multi-régimes et comparer DESIGN / VALIDATION / OOS avec les quatre vues 23A avant toute proposition de tuning. Une modification de seuil Scanner, de règle Professor ou de Risk devra être traitée comme une hypothèse distincte et validée hors échantillon, pas comme une conséquence automatique d'un agrégat descriptif.
<!-- BATCH24A1_ROADMAP -->
## Batch 24 — Analytics Lab & Decision Intelligence

### 24A.1 — Foundation, Contracts & Isolation Guards

Fondation observation-only : identité `AnalyticsLabRun`, provenance
dataset/as-of/MTF, versions, snapshots/manifeste/fingerprints déterministes et
guards AST. Aucun indicateur, event, ZigZag, pattern, attribution ou UI n'est
inclus.

Sous-batchs suivants explicitement hors scope de 24A.1 : 24A.2 Indicators,
24A.3 Technical Events, 24A.4 ZigZag, 24A.5 Patterns, 24A.6 Calibration,
24A.7 Contexts/Sequences, 24B Attribution, 24C Frontend, 24D Decision Quality
Research.

<!-- BATCH_24A2_RICH_INDICATORS -->
### Batch 24A.2 — Rich Indicators & Parity Catalogue

24A.2 installs the observation-only rich indicator catalogue and explicit semantic parity catalogue. Technical Events (24A.3), causal structure/ZigZag (24A.4), patterns and forward-outcome research remain out of scope.

<!-- BATCH_24A3_TECHNICAL_EVENTS -->
## Batch 24A.3 — Technical Events — livré dans l'Analytics Lab

Après 24A.1 (foundation/isolation) et 24A.2 (rich indicators), 24A.3 ajoute le registry
versionné de Technical Events, la détection causale T-1/T, les IDs/fingerprints stables,
l'evidence et l'intégration `AnalyticsSnapshot`. Le prochain sous-batch Analytics prévu
reste 24A.4 — Causal Structure & ZigZag; aucun pivot/pattern/context n'est implémenté ici.

<!-- BATCH_24A4_CAUSAL_STRUCTURE_ZIGZAG -->
## Batch 24A.4 — Causal Structure & ZigZag

24A.4 installe la projection de structure Money Heist et le ZigZag causal.
Patterns/lifecycle restent 24A.5 ; calibration 24A.6 ; contexts/sequences 24A.7.

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
## Addendum Batch 24A.7 — Analytics Core

24A.7 complète le noyau Analytics avec des Contexts et Sequences causaux observation-only. La phase suivante reste Batch 24B — Decision ↔ Analytics Attribution ; aucun join Scanner/Opportunity n'est ajouté par 24A.7.

<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Addendum Batch 24B — Decision ↔ Analytics Attribution

Roadmap de la phase :

```text
24B.1 — Opportunity ↔ Analytics Linking
24B.2 — Decision Intelligence Record
24B.3 — Scanner ↔ Analytics Attribution
24B.4 — Funnel Stage ↔ Analytics Attribution
```

24B.1 livre uniquement la primitive de jointure exacte et les diagnostics de
provenance. Il ne
construit ni Decision Intelligence Record, ni attribution complète Scanner/Funnel,
ni UI.

<!-- BATCH_24B2_DECISION_INTELLIGENCE_RECORD -->
## État Batch 24B.2 — Decision Intelligence Record

24B.2 introduit la projection read-only d'une opportunité complète avec son link Analytics 24B.1.
Le batch prépare 24B.3/24B.4/24C sans commencer leurs analyses, statistiques ou API/UI.
