# Money Heist — État actuel post-Batch 19

**Statut :** référence d’alignement active  
**Date :** 2026-09-09  
**Nom de fichier conservé :** `00_ETAT_ACTUEL_POST_BATCH_15.md` pour continuité des références existantes  
**Baseline d’entrée Batch 19 :** `96b2288` — `feat(evaluation): complete Batch 18 reputation and ablation`

---

## 1. État intégré

Les fondations 01 à 18 sont complétées et le **Batch 19 — Recruitment Engine** ajoute une couche de recrutement d’agents déterministe, auditable et advisory-only.

Le chemin de recrutement est maintenant :

```text
RecruitmentProposal
→ RecruitmentCandidateSpec
→ lifecycle candidat séparé
→ gates population / fréquence / compute
→ campagne BASELINE vs WITH_CANDIDATE
→ Historical Replay / PAPER isolé
→ comparabilité + provenance + OOS gate
→ AblationComparison Batch 18
→ réputation multidimensionnelle + coûts candidat
→ Candidate Evidence Package
→ Recruitment Advisory
→ Transition Planning opérateur-gaté
→ Audit FRESH / STALE
```

Le Recruitment Engine **n'arme pas le LIVE**, ne modifie pas le Risk Engine et ne crée pas automatiquement d’`AgentRegistryEntry`.

---

## 2. Lifecycle candidat

Le candidat reste hors `AgentRegistry` pendant son évaluation :

```text
PROPOSED
→ CANDIDATE
→ SHADOW
→ PROBATION
→ PROMOTION_RECOMMENDED

ou
→ REJECTED
```

`PROMOTION_RECOMMENDED` est une recommandation organisationnelle. Ce n’est ni `ACTIVE`, ni `ON_DEMAND`, ni une permission de trading LIVE.

Toute transition matérielle reste explicitement opérateur-gatée.

---

## 3. Campagnes de recrutement

Les campagnes comparent deux twins déterministes :

```text
BASELINE
= crew incumbent

WITH_CANDIDATE
= même crew + candidate:<recruitment_id>
```

Les twins partagent dataset, période et configuration matérielle. Chaque variante reçoit un HistoricalReplayRunner et un PaperBroker distincts afin d’éviter toute contamination d’état.

Les résultats DESIGN et VALIDATION peuvent servir au diagnostic. Une preuve destinée à la progression vers une promotion doit être OOS et comparable.

---

## 4. Réutilisation Batch 18

Le candidat réutilise les mécanismes Batch 18 sans dupliquer les calculs :

- `WITH_CANDIDATE` est le système complet contenant l’agent évalué ;
- `BASELINE` joue le rôle du système sans cet agent ;
- `compare_ablation()` produit les deltas trading, Economic Net, drawdown et coût IA ;
- la réputation reste multidimensionnelle ;
- aucun score magique n’est introduit.

Les coûts gardent deux dimensions distinctes :

```text
candidate_direct_ai_cost_eur
marginal_total_ai_cost_eur
```

Le coût directement attribué au candidat ne doit pas être confondu avec la variation totale de consommation IA du système.

---

## 5. Evidence Package et advisory

Le paquet d’évidence fige notamment :

- CandidateSpec ;
- critères de succès pré-enregistrés ;
- campagne et run IDs ;
- fingerprints ;
- provenance dataset/période ;
- rapports business ;
- comparaison Batch 18 ;
- réputation multidimensionnelle ;
- coûts candidat.

Les avis possibles sont :

```text
REJECT
EXTEND
PROBATION
RECOMMEND_PROMOTION
```

Une métrique obligatoire indisponible ne reçoit pas de valeur inventée : l’avis est `EXTEND`. Un critère mesuré qui échoue ou un budget candidat dépassé peut produire `REJECT`.

---

## 6. Transition planning et audit

Un avis peut être transformé en plan seulement après revalidation du contexte :

- lifecycle courant et révision ;
- CandidateSpec ;
- Evidence Package ;
- advisory ;
- politique et snapshot de capacité ;
- limites de population et de fréquence ;
- budget opérateur.

Le résultat reste :

```text
READY ou BLOCKED
```

`READY` signifie « présentable à l’opérateur », jamais « appliqué ».

L’audit `FRESH / STALE` empêche la réutilisation silencieuse d’un plan après modification de contexte. Un plan `STALE` doit être régénéré.

---

## 7. Surface API

La surface HTTP officielle Batch 19 est volontairement read-only :

```text
GET /api/recruitment/capabilities
mode = ADVISORY_READ_ONLY
```

Elle expose les capacités et frontières du Recruitment Engine, mais aucun endpoint HTTP de transition, promotion, mutation de registre ou autorité LIVE.

Les contrats Python publics sont exportés par `app.recruitment`.

---

## 8. Invariants de sécurité

Les invariants suivants restent obligatoires :

```text
auto_apply = False
registry_mutation = False
lifecycle_transition_applied = False
promotion_applied = False
live_authority = False
operator_authorization_required = True
```

Le Risk Engine déterministe reste l’autorité de risque. Le Recruitment Engine n’ajoute aucun bypass de risque, aucun ordre LIVE et aucun accès secret privilégié au candidat.

---

## 9. Frontière avec le LIVE

Le projet dispose de composants LIVE sécurisés issus des Batchs 14–15, mais le recrutement d’un agent est une décision séparée de l’activation du trading LIVE.

Aucune preuve de recrutement, même OOS et favorable, ne remplace :

- les gates LIVE existants ;
- le preflight ;
- les contrôles de configuration ;
- l’armement explicite ;
- la décision opérateur.

---

## 10. Documentation de référence

Pour l’état courant, lire en priorité :

1. le code intégré sur `main` ;
2. ce document ;
3. `09_ROADMAP_DEVELOPPEMENT.md` ;
4. `10_DECISIONS_ET_CHANGELOG.md` ;
5. `11_BACKTESTING_ET_REPLAY_HISTORIQUE.md` ;
6. les addenda Batch 19 dans les documents de domaine sous `docs/`.

Le layout historique du dépôt est conservé : `01_PROJECT_MASTER.md`, `02_ARCHITECTURE.md` et `07_SECURITE_ET_OPERATIONS.md` sont des documents **docs-only** ; ils ne doivent pas être dupliqués à la racine.

---

## 11. Prochaine étape

La prochaine étape planifiée est :

**Batch 20 — Task Force Agents**

Elle devra réutiliser les frontières de recrutement maintenant auditées : mission limitée, durée/expiration explicite, budget, allowlist tools, absence d’autorité LIVE implicite et capacité opérateur-gatée.
