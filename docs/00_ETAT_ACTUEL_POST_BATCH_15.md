# Money Heist — Mémoire projet / état courant

**Statut :** contexte de démarrage canonique  
**Date de synchronisation :** 2026-09-20
**Référence distante auditée :** GitHub `Ax-07/Money-Heist`, branche `main`  
**Baseline intégrée auditée :** `3a966d2695b72944dd087236a0162609ba17537f`
**Dernier commit audité :** Shadow Attention v0 + Semantic v1 candidate
**Nom de fichier conservé :** `00_ETAT_ACTUEL_POST_BATCH_15.md` pour compatibilité avec les références existantes.

> Ce document doit rester court. Il sert à reconstruire rapidement le contexte du projet dans une nouvelle session. Les détails de domaine restent dans les documents spécialisés.

---

## 1. Ordre d’autorité

En cas de divergence :

1. code intégré sur GitHub `main` ;
2. ce document pour l’état courant et le handoff ;
3. `10_DECISIONS_ET_CHANGELOG.md` pour les décisions/ADR ;
4. `09_ROADMAP_DEVELOPPEMENT.md` pour la trajectoire ;
5. documents de domaine `01` à `12` et ADR spécialisés ;
6. conversations ChatGPT et notes temporaires uniquement si elles ont été intégrées au dépôt.

Une conversation n’est pas une source de vérité durable tant que l’information importante n’a pas été consolidée dans le dépôt.

---

## 2. Vision et invariants constitutionnels

Money Heist est une plateforme de trading crypto assistée par IA organisée autour d’une crew multi-agents.

Pipeline principal :

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
→ PAPER / SHADOW / LIVE selon autorisation
→ Evaluation / Lisbon
```

Invariants :

- l’IA propose ; le Risk Engine déterministe autorise ;
- aucune sortie LLM ne peut devenir directement un ordre ;
- `NO_TRADE` est une décision valide ;
- la capacité directionnelle du marché est explicite via `MarketPositioningMode` ; pour `SPOT_LONG_ONLY`, toute ouverture nette SHORT est interdite de façon déterministe, tandis qu'une vente de réduction/clôture d'un LONG reste autorisée ;
- le LIVE reste fail-closed et opérateur-gaté ;
- aucun droit de retrait ne doit être accordé aux clés de trading ;
- les secrets ne transitent pas dans les prompts ni dans le navigateur ;
- Historical Replay et `LIVE_EVAL` restent PAPER-only ;
- les couches Analytics / Decision Intelligence / Decision Quality sont observationnelles et ne disposent d’aucune autorité Scanner, Agents, Risk, PAPER ou LIVE ;
- DESIGN / VALIDATION / OOS restent séparés ;
- les Forward Outcomes sont post-hoc et ne sont jamais réinjectés dans la décision à T.

---

## 3. Stack intégrée

### Backend

- Python 3.13 ;
- `uv` + `pyproject.toml` ;
- FastAPI ;
- modèles typés / validation stricte ;
- SQLite + SQLAlchemy/Alembic pour la base locale historique du prototype ;
- tests via `pytest` ;
- qualité via Ruff.

### Frontend V2

- Next.js / React / TypeScript strict ;
- Tailwind ;
- TanStack Query ;
- Zod ;
- Zustand pour l’état UI global ;
- Lightweight Charts derrière un adapter ;
- cockpit unifié pour trading, backtests, replay, Analytics et Decision Intelligence.

Le backend reste l’autorité métier. Le frontend observe, filtre, navigue et présente des artefacts persistés ; il ne recalcule pas les décisions.

---

## 4. Market Data et exécution

Premier marché LIVE ciblé historiquement :

```text
Kraken Spot / EUR
BTC/EUR
ETH/EUR
SOL/EUR
```

Principes :

- Market Data normalisé derrière des adapters ;
- contraintes exchange partagées avec le Risk Engine / broker ;
- PaperBroker et LiveBroker séparés derrière des interfaces contrôlées ;
- double exécution interdite par idempotence / `client_order_id` ;
- réconciliation obligatoire pour le LIVE ;
- données stale ou incohérentes bloquent les nouvelles entrées concernées.

Le chemin LIVE existe techniquement mais aucune promotion ne doit être déduite d’un backtest ou d’un rapport de recherche.

---

## 5. Historical Replay / Backtesting

Le moteur historique réutilise les composants métier de production :

```text
Dataset historique immuable
→ ReplayClock
→ Feature Engine
→ Scanner
→ Compute Gate / Agents
→ TradeProposal
→ Risk Engine
→ PaperTradingPipeline
→ PaperBroker
→ cycle de vie historique
→ Evaluation
```

Garanties structurantes :

- no-look-ahead ;
- dataset content-addressed ;
- run reproductible et versionné ;
- `code_version`, `execution_model_version`, seed, Risk/Feature/Scanner/Prompts/Models dans l’identité du run ;
- frais et slippage explicites ;
- policy intrabar conservatrice ;
- séparation DESIGN / VALIDATION / OOS ;
- walk-forward V1 sans optimiseur automatique ;
- aucune dépendance du backtest vers l’exécution LIVE.

Le smoke `LIVE_EVAL` historique prouve la viabilité technique du pipeline IA → Risk → PAPER, pas sa rentabilité ni sa promotion LIVE.

Pour les campagnes empiriques BTC/USDC 1m, `scripts/market_data/build_campaign_prefix_datasets.py` génère localement des préfixes calendaires exacts 1/3/6/9 mois et référence le 12 mois canonique. Les fichiers restent sous `data/` (ignoré par Git) et ne retirent que la queue future, afin de préserver l’état récursif des indicateurs et l’historique MTF sur les timestamps conservés.

---

## 6. Agents et organisation adaptative

Crew principale :

- The Professor — orchestration ;
- Palermo — contradiction / Red Team ;
- Lisbon — économie IA ;
- Berlin — tendance/régime ;
- Tokyo — momentum ;
- Nairobi — structure/liquidité ;
- Rio — dérivés/sentiment selon données disponibles ;
- Denver — quant/statistiques internes.

Éléments intégrés au fil des batches :

- registry et versionnage des prompts ;
- réputation multidimensionnelle ;
- ablation / comparaisons ;
- Recruitment Engine advisory-only et opérateur-gaté ;
- Task Forces temporaires, budgétées et sans autorité LIVE ;
- Master Portfolio Layer / Master Professor advisory, sans substitution au Master Risk / Risk Engine.

Les prompts actifs restent natifs français tout en conservant les clés JSON, enums et identifiants machine. La version active du Professor est désormais v8 ; Palermo reste v4, Lisbon v2 et les spécialistes v6. Professor v8 reçoit les directions de trade autorisées par la capacité de marché et doit les respecter pendant FINALIZE. Le transport de prompt courant reste `money-heist.prompt-transport.v4`.

---

## 7. Prompt Cache et coûts IA

Deux mécanismes distincts existent :

1. Prompt Cache fournisseur OpenAI pour réduire le coût des préfixes stables lorsque la route le permet ;
2. cache de réponses Historical Replay `money-heist.backtest-ai-cache.v2`.

La comptabilité IA conserve les tokens/couts réels et les informations de cache nécessaires à l’évaluation économique.

Le cache ne change aucune autorité métier.

---

## 8. Frontend V2 — état fonctionnel

Le cockpit V2 couvre notamment :

- Trading Workspace ;
- Backtest Cockpit ;
- Historical Replay ;
- Decision Trace ;
- opportunités / ordres / positions / historique ;
- agents / Evaluation ;
- Analytics overlays ;
- Decision Intelligence Inspector ;
- filtres et navigation causale ;
- Research Explorer Decision Quality ;
- Datasets locaux de campagne 1 / 3 / 6 / 9 / 12 mois, validés côté backend puis importés dans la bibliothèque V2 persistée ;
- résultats Backtest en deux niveaux : `Résumé` opérateur par défaut et `Analyse avancée` à la demande.
- Decision Chart d'audit au timeframe de décision canonique, avec indicateurs Feature Engine, Professor FINAL, rejets Risk et exécutions PAPER réelles ;
- mode Terminal Pro (`Mixte / Trades / Décisions`), navigation des trades, résultat net, coûts et Trade Story `Professor → Risk → Entry → Exit` ;

Le chart distingue l’ancrage géométrique de l’instant causal de connaissance :

```text
event_at       vs available_at
pivot_at       vs confirmed_at
market_as_of   vs operational_at
```

Le navigateur peut masquer, filtrer, sélectionner et naviguer, mais ne recalcule pas Analytics, Scanner, agents, Risk ou Forward Outcomes. Le Résumé réutilise les métriques et `decision_funnel` déjà produits par le backend ; Replay, Analytics overlays, Decision Intelligence et Research ne sont chargés qu'à l'ouverture de l'Analyse avancée.

Le catalogue local de campagne est fail-closed : seules les entrées déclarées par le manifeste local sont proposées ; avant persistance V2, le backend vérifie taille, SHA-256 brut, nombre de candles et bornes, puis repasse le CSV dans le validateur historique canonique. Aucun chemin arbitraire du disque n’est exposé au navigateur.

Le Backtest Cockpit expose aussi la capacité de marché. Les campagnes Spot ciblées utilisent `SPOT_LONG_ONLY` par défaut : Professor/MOCK, Risk Engine et PaperBroker convergent sur l'interdiction d'ouvrir une position nette SHORT. `LONG_SHORT` reste disponible comme capacité explicite pour des runtimes dérivés futurs.

---

## 9. Pile 23A — mesure causale et Forward Outcomes

Livré :

- 23A.1 — Decision Funnel Baseline ;
- 23A.2 — Forward Outcomes H1/H3/H5/H10/H20 ;
- 23A.3 — Funnel Outcome Attribution ;
- 23A.4 — Scanner Forward Outcomes.

Ces couches sont descriptives et post-hoc.

Règles :

- future price outcome ≠ PnL hypothétique ;
- `NO_TRIGGER` + mouvement futur ≠ trade automatiquement raté ;
- `NO_TRADE` + mouvement défavorable ≠ décision automatiquement « bonne » ;
- aucun tuning automatique de seuil ;
- aucun feedback vers `DecisionContext`.

---

## 10. Batch 24A — Analytics Lab

24A est livré comme couche observation-only.

Sous-batches :

```text
24A.1 Foundation / isolation
24A.2 Rich Indicators / parity catalogue
24A.3 Technical Events
24A.4 Causal Structure & ZigZag
24A.5 Patterns & causal lifecycle
24A.6 Pattern calibration / pivot-source diagnostics
24A.7 Contexts & Sequences
```

Principes :

- identité Analytics distincte du `BacktestRun` ;
- provenance dataset/as-of/MTF explicite ;
- indicateurs et registries versionnés ;
- Technical Events causaux ;
- ZigZag causal ;
- patterns `FORMING / CONFIRMED / FAILED / INVALIDATED` ;
- aucune back-propagation du statut final ;
- aucune autorité trading.

Le commit `c28b71d` corrige explicitement la causalité du timing des transitions de patterns : le lifecycle ne peut pas devenir disponible avant la confirmation causale du dernier pivot requis.

---

## 11. Batch 24B — Decision ↔ Analytics Attribution

Livré :

```text
24B.1 Opportunity ↔ Analytics Linking
24B.2 Decision Intelligence Record
24B.3 Scanner ↔ Analytics Attribution
24B.4 Funnel Stage ↔ Analytics Attribution
```

Règles :

- exact matching de provenance ;
- pas de nearest-neighbor temporel implicite ;
- `FeatureSnapshot.snapshot_id` reste l’identité canonique d’une évaluation Scanner ;
- le funnel conserve `market_as_of` et `operational_at` ;
- les failures techniques restent distinctes des décisions métier ;
- Analytics non résolu ne doit pas être fabriqué ou rematché.

---

## 12. Batch 24C — Decision Intelligence Backend & UI

Livré :

```text
24C.1 Backend Projection API
24C.2 Trading Chart Analytics Overlays
24C.3 Decision Intelligence Inspector
24C.4 Filters & Navigation
```

Architecture :

```text
artefacts canoniques backend
→ projections persistées post-run
→ GET read-only
→ frontend
```

Les filtres et la navigation sont UI-only. Ils n’altèrent ni les artefacts canoniques ni le business fingerprint.

---

## 13. Batch 24D — Decision Quality Research

État intégré observé sur `main` :

```text
24D.1 Research Foundation & Outcome Join          DONE
24D.2 Scanner Filtering Quality Research          DONE
24D.3 Funnel Decision Quality Research            DONE
24D.4 Research Reports & Evidence Explorer        DONE
```

24D.1 crée une jointure déterministe entre Decision Intelligence / Scanner / Analytics et les Forward Outcomes canoniques.

24D.2 mesure descriptivement les cohortes Scanner (`NO_TRIGGER`, `TRIGGER_BELOW_CANDIDATE_THRESHOLD`, `CANDIDATE_OPPORTUNITY`) par classification, score, marge, triggers et régime sans recommander de seuil.

24D.3 mesure descriptivement les stages du funnel. Les stages antérieurs à Professor FINAL restent directionless ; les stages aval peuvent utiliser une direction LONG/SHORT uniquement si elle était déjà causalement connue.

24D.4 branche la recherche dans le post-run, persiste les sidecars, expose des GET read-only et ajoute le Research Explorer frontend avec Evidence Index.

Ordre post-run :

```text
24A Analytics
→ 24B Attribution / Decision Intelligence
→ 24C projections frontend
→ 24D.1 Research Bundle
→ 24D.2 Scanner Filtering Quality
→ 24D.3 Funnel Decision Quality
→ 24D.4 Evidence Index
```

Exports 24D.4 par rôle :

- `decision-quality-research-{role}.json` ;
- `scanner-filtering-quality-{role}.json` ;
- `funnel-decision-quality-{role}.json` ;
- `decision-quality-evidence-{role}.json`.

Aucun rapport 24D ne peut recommander automatiquement un threshold, classer automatiquement un agent, produire une autorité de tuning ou modifier LIVE.

---


### Shadow Attention — état validé

La recherche Scanner ↔ Analytics a confirmé un biais de sélection Scanner vers `RANGE_BREAK`
et un fort volume d'observations Analytics ignorées par la gate historique. Une couche
**Shadow Attention** a donc été ajoutée uniquement au post-run, sans autorité métier.

État figé au commit `3a966d2695b72944dd087236a0162609ba17537f` :

- **Shadow Attention v0** : projection observation-only des impulsions causales issues des
  `Technical Events`, confirmations ZigZag et transitions de patterns ;
- **Semantic v1 candidate** : `WAKE` si, au même instant causal, il existe soit au moins
  deux familles techniques distinctes, soit `Technical Event + ZigZag confirmé`, soit une
  transition de pattern mature `CONFIRMED / FAILED / INVALIDATED` ;
- la structure seule reste du contexte et ne réveille pas la candidate ;
- aucune direction de trade, aucun score, aucun cooldown, aucun Forward Outcome et aucun
  résultat MOCK n'entrent dans la policy ;
- v0 et v1 restent **SHADOW / observation-only** et ne modifient ni Scanner, ni Agents,
  ni Risk, ni PAPER, ni LIVE ;
- la campagne 3 mois utilisée pour concevoir cette candidate est désormais exploratoire
  et ne constitue plus un holdout de validation.

La suite complète locale a été exécutée après intégration de la candidate :
`uv run pytest -q` passe avec 3 skips attendus. Ruff ciblé et `git diff --check`
sont également propres.

## 14. Baseline intégrée récente

La baseline applicative auditée pour cette synchronisation est `3a966d2695b72944dd087236a0162609ba17537f`.

Chaîne récente utile :

```text
b384852e  feat(backtest): enforce spot long-only campaigns
871a3d3f  feat(frontend): simplify backtest campaign results
bc6136ee  docs: sync project memory after backtest UX
8f707cb8  fix(backtest): keep API responsive during post-run analysis
```

Le lot de réactivité Backtest a été validé avant intégration par la suite backend complète `uv run pytest -q` avec 3 skips attendus, les tests ciblés `test_backtest_controls.py` et `test_frontend_v2.py`, Ruff, 67 tests frontend et `pnpm run typecheck`. Les calculs post-run 23A/24A→24D restent identiques mais sont déportés hors de l'event loop FastAPI afin que `/progress`, `/capabilities` et les routes read-only restent servables pendant les campagnes longues. Aucune autorité Scanner, Professor, Risk, PAPER ou LIVE n'a été déplacée.

Les documents de livraison des anciens batches sont désormais conservés sous `docs/archives/`.
Ils sont historiques et ne définissent pas l'état courant ; les documents actifs `00` à `12`, les ADR et le code intégré gardent cette responsabilité.

---

## 15. LIVE — gates toujours ouvertes

Avant tout premier ordre réel, la gate reste au minimum :

```text
backtests reproductibles multi-régimes
+ critères prédéfinis
+ VALIDATION
+ OOS
+ walk-forward
+ PAPER / SHADOW prolongé
+ paramètres Balanced numériques explicitement validés
+ timeframes de production validés
+ seuils de fraîcheur Market Data validés
+ sécurité / réconciliation / preflight
+ décision opérateur explicite
```

Le capital initial visé reste faible et le premier LIVE historique ciblé reste Spot / EUR sans marge ni levier. La capacité correspondante est `SPOT_LONG_ONLY` : une proposition SHORT d'ouverture est rejetée déterministiquement et ne peut pas atteindre l'exécution réelle.

Aucune couche Analytics/Research ne ferme automatiquement cette gate.

---

## 16. Priorité de développement après cette synchronisation

La phase de recherche Shadow Attention est désormais figée sur une candidate sémantique
**observation-only**. Il ne faut plus ajuster cette policy sur la campagne 3 mois qui a servi
à sa conception.

Priorités :

1. conserver la policy Semantic v1 inchangée ;
2. choisir une **nouvelle période fraîche** qui n'a pas servi aux audits de conception ;
3. exécuter Shadow v0 et Semantic v1 sur cette période sans modifier Scanner, prompts, Risk
   ou exécution ;
4. vérifier stabilité de charge, couverture causale, qualité des joins et coût théorique ;
5. seulement après cette validation, décider s'il existe une justification pour un batch
   comportemental séparé ;
6. préserver un véritable OOS pour toute promotion ultérieure ;
7. maintenir PAPER / SHADOW avant toute discussion LIVE.

Aucune métrique de cette campagne exploratoire ne constitue une autorisation pour remplacer
Scanner v1 dans le pipeline comportemental.

## 17. Handoff pour une nouvelle conversation

Au début d’une nouvelle session Money Heist :

```text
1. lire ce fichier ;
2. vérifier le HEAD actuel de GitHub main ;
3. si HEAD != baseline intégrée auditée de ce fichier, inspecter les commits depuis cette baseline ;
4. lire uniquement les documents de domaine nécessaires à la tâche ;
5. consulter 10_DECISIONS_ET_CHANGELOG pour le pourquoi ;
6. consulter 09_ROADMAP_DEVELOPPEMENT pour la suite ;
7. ne pas reconstruire l’état du projet à partir d’anciennes conversations seules.
```

Informations de handoff obligatoires après un gros lot :

- `HEAD` ;
- dernier batch/sous-batch terminé ;
- tests réellement exécutés ;
- fichiers volontairement non commités si connus ;
- problème actif ;
- décisions prises ;
- prochaine étape exacte.

---

## 18. Limite de cette synchronisation

Cette synchronisation a audité GitHub `main` jusqu'au commit `3a966d2695b72944dd087236a0162609ba17537f`. Elle ne décrit pas automatiquement de futures modifications locales non commités ; un handoff local doit toujours signaler explicitement un working tree sale avant de considérer ce fichier comme exhaustif.

---

## 19. Règle d’entretien

Ce fichier doit rester une **mémoire courte**, pas un changelog exhaustif.

À chaque gros lot :

1. mettre à jour la baseline intégrée auditée + date ;
2. remplacer l’état courant au lieu d’empiler des sections obsolètes ;
3. mettre les décisions dans `10_DECISIONS_ET_CHANGELOG.md` ;
4. mettre les travaux futurs dans `09_ROADMAP_DEVELOPPEMENT.md` ;
5. garder ici uniquement ce qu’une nouvelle session doit savoir pour reprendre correctement le projet.

<!-- DECISION_CHART_TERMINAL_PRO_20260920 -->
