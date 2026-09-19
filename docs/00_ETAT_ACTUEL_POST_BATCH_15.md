# Money Heist — Mémoire projet / état courant

**Statut :** contexte de démarrage canonique  
**Date de synchronisation :** 2026-09-19  
**Référence distante auditée :** GitHub `Ax-07/Money-Heist`, branche `main`  
**HEAD audité :** `c28b71d55387e9d6dd84cfee475d83b9640c3404`  
**Dernier commit :** `fix(analytics): enforce causal pattern transition timing`  
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

Les prompts actifs ont été migrés vers un dialogue natif français tout en conservant les clés JSON, enums et identifiants machine. Le transport de prompt courant après cette migration est `money-heist.prompt-transport.v4`.

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
- Research Explorer Decision Quality.

Le chart distingue l’ancrage géométrique de l’instant causal de connaissance :

```text
event_at       vs available_at
pivot_at       vs confirmed_at
market_as_of   vs operational_at
```

Le navigateur peut masquer, filtrer, sélectionner et naviguer, mais ne recalcule pas Analytics, Scanner, agents, Risk ou Forward Outcomes.

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

Le HEAD `c28b71d` corrige explicitement la causalité du timing des transitions de patterns : le lifecycle ne peut pas devenir disponible avant la confirmation causale du dernier pivot requis.

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

## 14. Derniers commits intégrés après 24D.4

À la synchronisation :

```text
a03ade86  feat(research): add research reports and evidence explorer
f9061e06  chore(quality): close static hygiene gate
faf713c4  style(prompts): normalize prompt formatting
c28b71d5  fix(analytics): enforce causal pattern transition timing
```

Ces commits sont postérieurs à plusieurs sections documentaires qui indiquent encore 24D.2/24D.3 comme `CURRENT`. Ces marqueurs historiques ne doivent donc pas être interprétés comme l’état courant.

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

Le capital initial visé reste faible et le premier LIVE historique ciblé reste Spot / EUR sans marge ni levier.

Aucune couche Analytics/Research ne ferme automatiquement cette gate.

---

## 16. Priorité de développement après cette synchronisation

La construction 24D est suffisamment avancée pour passer de « construire les instruments de mesure » à « exploiter proprement les preuves ».

Priorités de recherche :

1. campagnes historiques longues et multi-régimes ;
2. analyse séparée DESIGN / VALIDATION / OOS ;
3. vérification de couverture et qualité des joins avant interprétation ;
4. formulation d’hypothèses de modification à partir de DESIGN seulement ;
5. validation de toute hypothèse sur des données non utilisées pour la concevoir ;
6. comparaison coûts IA / qualité décisionnelle / pertes du funnel ;
7. maintien du LIVE non promu tant que les gates opérateur ne sont pas satisfaites.

Aucune modification de threshold Scanner, prompt, Risk ou exécution ne doit être déduite automatiquement d’un rapport descriptif.

---

## 17. Handoff pour une nouvelle conversation

Au début d’une nouvelle session Money Heist :

```text
1. lire ce fichier ;
2. vérifier le HEAD actuel de GitHub main ;
3. si HEAD != HEAD de ce fichier, inspecter les commits depuis cette baseline ;
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

Cette synchronisation voit GitHub `main` jusqu’à `c28b71d55387e9d6dd84cfee475d83b9640c3404`.

Elle ne peut pas connaître automatiquement les modifications non commités présentes sur une machine locale après ce commit. Un handoff local doit donc signaler explicitement un working tree sale ou des correctifs en cours avant de considérer ce fichier comme exhaustif.

---

## 19. Règle d’entretien

Ce fichier doit rester une **mémoire courte**, pas un changelog exhaustif.

À chaque gros lot :

1. mettre à jour HEAD + date ;
2. remplacer l’état courant au lieu d’empiler des sections obsolètes ;
3. mettre les décisions dans `10_DECISIONS_ET_CHANGELOG.md` ;
4. mettre les travaux futurs dans `09_ROADMAP_DEVELOPPEMENT.md` ;
5. garder ici uniquement ce qu’une nouvelle session doit savoir pour reprendre correctement le projet.
