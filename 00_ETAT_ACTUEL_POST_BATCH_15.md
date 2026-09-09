# Money Heist — État actuel post-Batch 20

**Statut :** référence d’alignement active  
**Date :** 2026-09-09  
**Nom de fichier conservé :** `00_ETAT_ACTUEL_POST_BATCH_15.md` pour continuité des références  
existantes  
**Baseline d’entrée Batch 20 :** `572cd07` —  
`feat(recruitment): complete Batch 19 Recruitment Engine`

---

## 1. État intégré

Les Batchs 01 à 20 sont livrés. Le **Batch 20 — Task Force dynamique** ajoute une couche
multi-agents temporaire, déterministe, auditable et advisory-only pour les analyses complexes ou
exceptionnelles.

Le chemin intégré est maintenant :

```text
TaskForceTriggerSignal explicite
→ TaskForceRequest
→ policy opérateur + gates population/capability/budget
→ composition registry-only + réputation multidimensionnelle
→ provenance / stale audit
→ TaskForcePlan PLANNED
→ autorisation opérateur
→ TaskForceExecutionContract
→ compute gate par membre
→ AI Gateway
→ TaskForceMemberAnalysis
→ agrégation provenance-preserving
→ TaskForceReport
→ bridge grounded vers The Professor
→ orchestration principale inchangée
→ Palermo principal
→ Professor final
→ TradeProposal éventuel
→ Risk Engine déterministe
```

La Task Force ne devient jamais une autorité de trading.

---

## 2. Composition et lifecycle

Une Task Force est temporaire et bornée par :
- une mission et une question explicites ;
- une date d’expiration ;
- une policy opérateur de population, coût, appels et retries ;
- une allowlist tools qui ne peut pas dépasser celle du registre ;
- des rôles/capabilities explicitement demandés ;
- des fingerprints déterministes.

La composition sélectionne uniquement des agents réellement présents dans `AgentRegistry`. Un
candidat Recruitment Batch 19 ne peut pas être utilisé tant qu’il n’est pas devenu une entrée
opérationnelle du registre par un processus externe autorisé.

Le lifecycle est :

```text
PLANNED
→ APPROVED_FOR_EXECUTION
→ RUNNING
→ COMPLETED / FAILED / CANCELLED

PLANNED / APPROVED
→ BLOCKED / CANCELLED
```

Le passage vers `APPROVED_FOR_EXECUTION` exige une autorisation opérateur explicite.

---

## 3. Réputation et composition

La réputation Batch 18 est consommée comme preuve multidimensionnelle. Aucun score magique de
réputation ou de consensus n’est calculé.

Les priorités de composition sont explicites et opérateur-owned : état, dimensions de réputation,
capabilities et taille cible. Un changement du registre, des capabilities, des preuves de réputation
ou des policies rend la composition `STALE` et impose une recomposition.

---

## 4. Exécution IA

Chaque membre passe par :

```text
TaskForceComputeQuote
→ TaskForce compute gate
→ AIGateway.generate_structured()
→ TaskForceMemberAnalysis
```

Le budget Task Force est un sous-plafond. Il ne remplace jamais le hard budget du Batch 06 AI
Gateway. Les appels providers directs sont interdits.

En cas de compute gate refusée, dépassement de quote, erreur Gateway, identité incohérente ou
comptabilité de coût non fiable, l’exécution s’arrête fail-closed.

---

## 5. Agrégation et Red Team

L’agrégation conserve les contributions individuelles : réponses, findings, evidence refs,
incertitudes, questions de suivi, coûts et latences.

```text
aggregation_method = PROVENANCE_PRESERVING_NO_SEMANTIC_VOTE
semantic_consensus_computed = False
aggregate_confidence_computed = False
```

Si un Red Team temporaire est requis, il doit déjà être couvert par la composition et exécuté comme
membre. Cette contribution ne remplace pas le `PalermoReview` du pipeline principal.

---

## 6. Intégration orchestration

Le déclenchement ne repose sur aucun seuil caché. Un `TaskForceTriggerSignal` explicite est
requis et
la policy opérateur décide quels triggers sont activés.

Un `TaskForceReport` consommé par l’orchestration est revalidé contre l’opportunité, le snapshot, la
fenêtre temporelle et son fingerprint. Il est exposé uniquement au Professor final comme nouvelle
source grounded `task_force_report.*`.

Il n’est pas injecté dans Palermo et ne court-circuite aucune étape du pipeline historique.

---

## 7. Evaluation et replay

Batch 20e fournit :
- coût réel total et par agent ;
- appels, attempts, latence et taille de Task Force ;
- comptage findings/incertitudes/questions ;
- deltas Trading Net / Economic Net / drawdown uniquement avec baseline comparable ;
- campagne Historical Replay `BASELINE` vs `WITH_TASK_FORCE` ;
- runner et PaperBroker isolés par twin ;
- replay PAPER-only ;
- seal de reproductibilité et audit `FRESH / STALE`.

Sans baseline comparable, les métriques économiques marginales restent `UNAVAILABLE`.

---

## 8. Invariants d’autorité

Les contrats Batch 20 préservent systématiquement :

```text
advisory_only = True
auto_execute = False
registry_mutation = False
risk_authority = False
live_authority = False
```

L’autorité Risk reste le moteur déterministe existant. L’armement LIVE Batch 15 reste séparé et
explicite.

---

## 9. Frontière avec Recruitment

Recruitment décide si un candidat mérite une progression organisationnelle. Task Force compose et
exécute temporairement des agents déjà disponibles dans le registre.

Aucune Task Force ne peut transformer un candidat Recruitment en agent opérationnel, modifier son
lifecycle ou contourner les gates de promotion Batch 19.

---

## 10. Documentation de référence

Pour l’état courant, lire en priorité :
1. le code intégré sur `main` ;
2. ce document ;
3. `09_ROADMAP_DEVELOPPEMENT.md` ;
4. `10_DECISIONS_ET_CHANGELOG.md` ;
5. `11_BACKTESTING_ET_REPLAY_HISTORIQUE.md` ;
6. les addenda Batch 20 des documents de domaine sous `docs/`.

Le layout historique reste inchangé : `01_PROJECT_MASTER.md`, `02_ARCHITECTURE.md` et
`07_SECURITE_ET_OPERATIONS.md` restent docs-only.

---

## 11. Prochaine étape

La prochaine étape de roadmap est **Batch 21 — Master Portfolio Layer**.

Elle ne doit pas être confondue avec une autorisation de premier ordre réel : les bloqueurs LIVE
existants, les campagnes historiques/PAPER/SHADOW et le preflight restent applicables.
