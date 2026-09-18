# Batch 24D.4 — Research Reports & Evidence Explorer

## Statut

Implémentation du pipeline post-run de consultation des rapports **Decision Quality** et de leurs observations sources, sans modification des autorités opérationnelles Scanner / Agents / Risk / PAPER / LIVE.

## Chaîne post-run

Pour chaque rôle `DESIGN`, `VALIDATION` et `OOS`, le post-traitement conserve l'ordre suivant :

1. 24A — Analytics Lab ;
2. 24B — attribution Analytics et Decision Intelligence ;
3. 24C — projections frontend ;
4. 24D.1 — Decision Quality Research Bundle ;
5. 24D.2 — Scanner Filtering Quality ;
6. 24D.3 — Funnel Decision Quality ;
7. 24D.4 — Evidence Index.

Les Forward Outcomes 23A déjà produits pendant le replay sont réutilisés. Le post-run ne recalcule aucun outcome et ne rejoue aucune autorité métier.

## Exports persistés

Chaque rôle produit quatre nouveaux sidecars JSON :

- `decision-quality-research-{role}.json`
- `scanner-filtering-quality-{role}.json`
- `funnel-decision-quality-{role}.json`
- `decision-quality-evidence-{role}.json`

Le mécanisme existant `FrontendV2Store.snapshot_terminal()` persiste ces exports avec les autres artefacts de campagne.

## Evidence Index

L'index est normalisé : les observations sont stockées une fois, puis les cohortes pointent vers leurs `ref_id`.

Un sélecteur de cohorte est défini par :

```text
report_type + stage? + dimension + key
```

Les contrastes conservent deux sélecteurs indépendants, `left` et `right`.

### Scanner

L'appartenance à une cohorte Scanner est reconstruite uniquement à partir du bloc causal 24D.1 :

- classification ;
- score ;
- score margin ;
- triggers ;
- market regime.

Ni `future_outcome` ni les métriques post-hoc ne participent à cette sélection. L'identité d'evidence Scanner utilise le `causal_fingerprint`.

Navigation replay : `observed_at`.

### Funnel

L'appartenance Funnel réutilise exactement les `member_refs` déjà figés par 24D.3 et les résout vers les records d'attribution de stage.

Navigation replay : `operational_at ?? market_as_of`.

## API read-only

Endpoints :

```text
GET /api/frontend/v2/backtests/runs/{campaign_id}/research/decision-quality?role=OOS

GET /api/frontend/v2/backtests/runs/{campaign_id}/research/evidence
    ?role=OOS
    &report_type=SCANNER_FILTERING
    &dimension=CLASSIFICATION
    &key=CANDIDATE_OPPORTUNITY
    &page=1
    &page_size=25
```

Les routes GET chargent uniquement des sidecars pré-calculés. Aucun builder 24D n'est appelé depuis l'API.

Les anciens runs sans artefacts 24D.4 restent consultables : le rapport renvoie explicitement `PRECOMPUTED_RESEARCH_UNAVAILABLE`.

## Frontend

Le détail d'un backtest contient un **Research Explorer** read-only :

- workspace Scanner Filtering Quality ;
- workspace Funnel Decision Quality ;
- vues Cohorts / Contrasts / Coverage ;
- chargement paginé des evidences ;
- deux panneaux d'evidence indépendants pour un contrast ;
- synchronisation d'une evidence avec le replay et le Decision Intelligence Inspector via l'`OverlaySelection` existante.

Les sélections de cohort/contrast sont des états UI temporaires Zustand. Elles ne sont pas persistées et ne remplacent pas l'autorité de sélection replay existante.

## Garde-fous

Ce batch reste descriptif et post-hoc :

- aucune recommandation de seuil ;
- aucun classement "best/winner" ;
- aucune affirmation causale ;
- aucun stop/target/PnL contrefactuel ;
- aucune agrégation entre DESIGN / VALIDATION / OOS ;
- aucune mutation LIVE ;
- aucune modification des modèles ou fingerprints 24D.2 / 24D.3.

L'OOS reste un rôle distinct et explicitement identifié dans l'interface.
