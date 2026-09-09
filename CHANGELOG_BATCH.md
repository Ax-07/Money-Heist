# Batch 18a — Réputation et ablation — clôture des fondations

## État

Steps 1 à 4 livrés et conçus comme une couche d’évaluation déterministe/advisory-only.

## Step 1 — Fondations réputation + ablation

- comparaison stricte baseline vs run sans exactement un agent ;
- comparabilité par fingerprint expérimental, dataset, rôle, période, bougies et opportunités ;
- deltas Trading Net / Economic Net / drawdown / coût IA ;
- agrégation d’ablation ;
- `AgentReputationProfile` multidimensionnel ;
- aucune mutation runtime.

## Step 2 — Policy de recommandation d’état

- `AgentStateEvidence` ;
- seuils explicites `ReputationPolicyThresholds` ;
- recommandations `HOLD / PROMOTE / DEMOTE / REDUCE_FREQUENCY` ;
- transitions progressives ;
- fonctions Core protégées ;
- `auto_apply=False`.

## Step 3 — Bridge et rapport auditable

- `ReputationAdvisoryService` ;
- adaptation Step 1 → Step 2 ;
- ablation OOS-only pour la preuve de transition ;
- contrôle du scope de coût IA ;
- provenance runs/datasets/fingerprints ;
- `AgentReputationAdvisoryReport` avec fingerprint SHA-256 déterministe.

## Step 4 — API publique, exports et documentation

- consolidation des exports publics dans `app/evaluation/__init__.py` ;
- `reputation_advisory_to_dict()` / `reputation_advisory_to_json()` ;
- sérialisation JSON-safe des Decimal/enums/dataclasses sans mutation ;
- updater documentaire idempotent pour Evaluation/API/Roadmap ;
- tests d’API publique, d’exports et de préservation documentaire.

## Frontières

Batch 18a ne :
- modifie pas automatiquement `AgentRegistry` ;
- ne fixe pas de seuil de production ;
- n’active pas le LIVE ;
- ne modifie pas le Risk Engine ni le broker ;
- ne considère pas l’ablation comme une preuve causale universelle ;
- ne transforme pas DESIGN/VALIDATION en OOS.

Les campagnes empiriques comparables et les critères opérateur pré-définis restent nécessaires avant
toute décision organisationnelle réelle sur un agent.

<!-- BATCH18B_STEP4_CHANGELOG_START -->

# Batch 18b — Ablation Campaign Runner — clôture

## Livré

- plan de campagne déterministe baseline + `WITHOUT_AGENT` ;
- `run_id` distinct par twin avec fingerprint de comparaison commun ;
- exécution Batch 16/PAPER isolée par variant ;
- conversion automatique en `BacktestPeriodReport` et `AblationComparison` ;
- rejet de toute réutilisation broker/runner entre twins ;
- PAPER Runtime Factory dans `app.services.backtest`, hors couche Evaluation ;
- spécialistes recréés avec un AI Gateway/budget/usage scope propre à chaque variant ;
- modes IA MOCK/CACHED/LIVE_EVAL conservés ;
- export compact JSON/dict du rapport de campagne ;
- exports publics lazy pour éviter les cycles Evaluation ↔ Backtest ;
- aucune mutation `AgentRegistry`, aucun bypass Risk et aucun trading LIVE.

## Clôture Batch 18

Batch 18a + 18b fournissent désormais l'infrastructure complète de réputation et d'ablation.
Une décision organisationnelle réelle reste conditionnée aux campagnes empiriques,
à l'OOS et aux
seuils opérateur pré-définis ; elle n'est jamais appliquée automatiquement.

<!-- BATCH18B_STEP4_CHANGELOG_END -->

<!-- BATCH19_CLOSURE_START -->

# Batch 19 — Recruitment Engine — clôture

## Livré

- contrats `RecruitmentProposal` / `RecruitmentCandidateSpec` et lifecycle candidat séparé ;
- gates déterministes population, fréquence et budget/compute ;
- campagnes twins `BASELINE` / `WITH_CANDIDATE` sur Historical Replay/PAPER ;
- isolation stricte runner/broker entre variantes ;
- comparabilité, provenance et gate OOS ;
- bridge vers `AblationComparison` et réputation multidimensionnelle Batch 18 ;
- distinction coût IA direct candidat / coût IA marginal système ;
- paquet d'évidence auditable et reproductible ;
- advisory `REJECT / EXTEND / PROBATION / RECOMMEND_PROMOTION` ;
- planning de transition opérateur-gaté ;
- audit `FRESH / STALE` et stale-plan guards ;
- exports publics `app.recruitment` ;
- API `GET /api/recruitment/capabilities` en mode `ADVISORY_READ_ONLY` ;
- documentation projet et ADR-026 réalignés.

## Frontières de clôture

Batch 19 ne :
- crée pas automatiquement d'`AgentRegistryEntry` candidat ;
- ne promeut pas automatiquement un candidat vers `ACTIVE` ou `ON_DEMAND` ;
- n'applique pas automatiquement les transitions de lifecycle ;
- ne modifie pas le Risk Engine ;
- n'accorde aucune autorité LIVE ;
- n'expose aucun endpoint HTTP Recruitment d'écriture.

Toute progression matérielle reste opérateur-gatée, fondée sur des critères pré-enregistrés et, pour la promotion, sur une preuve OOS comparable.

## Clôture documentaire

Le layout historique du dépôt est préservé : `01_PROJECT_MASTER.md`, `02_ARCHITECTURE.md` et `07_SECURITE_ET_OPERATIONS.md` restent docs-only et ne sont pas versionnés à la racine.

La prochaine étape de roadmap est **Batch 20 — Task Force Agents**.

<!-- BATCH19_CLOSURE_END -->

<!-- BATCH20_CLOSURE_START -->

# Batch 20 — Task Force dynamique — clôture

## Livré

- contrats Task Force temporaires avec mission, expiration, budget, appels et allowlist ;
- lifecycle `PLANNED → APPROVED_FOR_EXECUTION → RUNNING → terminal` ;
- gates population/capability/compute fail-closed ;
- composition déterministe registry-only ;
- réputation Batch 18 multidimensionnelle sans score magique ;
- provenance de composition, fingerprints et stale detection ;
- clôture de composition vers `TaskForcePlan` toujours `PLANNED` ;
- contrats d’exécution et appels multi-membres via AI Gateway uniquement ;
- comptabilité coût/attempts/latence et arrêt fail-closed ;
- agrégation provenance-preserving, sans vote sémantique ;
- Red Team temporaire optionnel sans remplacer Palermo principal ;
- trigger bridge explicite, sans seuil de complexité inventé ;
- intégration `TaskForceReport` grounded dans le Professor final ;
- Evaluation Task Force et contribution économique uniquement avec baseline comparable ;
- Historical Replay twins `BASELINE` / `WITH_TASK_FORCE` PAPER-only ;
- replay seal et audit `FRESH / STALE` ;
- exports publics consolidés.

## Frontières de clôture

Batch 20 ne :
- sélectionne pas un candidat Recruitment absent d'`AgentRegistry` ;
- ne modifie pas automatiquement le registre ou l’état d’un agent ;
- ne remplace pas le hard budget AI Gateway ;
- n’appelle pas directement un provider IA ;
- ne crée pas directement un `TradeProposal` depuis une Task Force ;
- ne contourne pas Palermo principal ni le Risk Engine ;
- n’accorde aucune autorité LIVE ;
- n’invente aucune métrique économique lorsqu’une baseline comparable est absente.

## Suite

La prochaine étape de roadmap est **Batch 21 — Master Portfolio Layer**. Les bloqueurs LIVE
existants
restent indépendants et doivent toujours être satisfaits avant tout premier ordre réel.

<!-- BATCH20_CLOSURE_END -->
