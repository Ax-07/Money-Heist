# Batch 24C.3 — Decision Intelligence Inspector

## Statut

Implémentation du Batch 24C.3 avec Gate 0 de persistance automatique des artefacts 24A/24B/24C.

Baseline d'entrée :

```text
repository: Ax-07/Money-Heist
branch: main
commit: 02226128e34cf88fbe2c9b1f9dff1d5b1f16267a
```

## Gate 0 — Persistance automatique

L'audit a montré que les helpers 24A, 24B, 24C.1 et 24C.2 existaient mais n'étaient pas branchés au chemin normal de fin de backtest.

Le chemin corrigé est désormais :

```text
Historical Replay terminé
  -> post-traitement Analytics 24A
  -> attributions 24B
  -> projection Decision Intelligence 24C.1
  -> projection géométrique 24C.2
  -> ajout aux CampaignSummary.exports
  -> FrontendV2Store.watch()
  -> snapshot_terminal()
  -> sidecars persistés
  -> GET read-only
```

Le calcul est réalisé avant la construction finale du `CampaignSummary`. Les endpoints GET restent strictement read-only et ne déclenchent aucun lazy-compute.

Sidecars générés pour chaque rôle :

```text
frontend-decision-intelligence-design.json
frontend-decision-intelligence-validation.json
frontend-decision-intelligence-oos.json
frontend-analytics-overlays-design.json
frontend-analytics-overlays-validation.json
frontend-analytics-overlays-oos.json
```

Le post-traitement ne rejoue jamais Scanner, agents, Risk Engine ou PAPER. Il reconstruit uniquement les artefacts Analytics observationnels nécessaires à partir du même univers historique causal.

## Inspector 24C.3

L'Inspector réutilise le panneau droit existant du Historical Replay et les états Zustand introduits en 24C.2 :

```text
selectedOpportunityId
selectedAnalyticsObject
inspectorOpen
```

Un clic sur un marker Analytics ouvre l'Inspector et synchronise l'opportunité associée lorsqu'elle existe.

Sections :

- Scanner ;
- Agents ;
- Decision Funnel ;
- Risk & Execution ;
- Analytics causal.

Le frontend consomme le détail 24C.1 existant :

```text
GET /api/frontend/v2/backtests/runs/{campaign_id}/opportunities/{opportunity_id}/decision-intelligence?role=...
```

Aucune nouvelle autorité métier n'est introduite.

## Causalité UI

L'Inspector distingue explicitement les horodatages lorsqu'ils sont disponibles :

- `available_at` pour les événements techniques ;
- `confirmed_at` pour les pivots ZigZag ;
- `operational_at` pour les étapes du funnel ;
- transitions de patterns selon leur disponibilité.

Les fingerprints de cursor source et de snapshot Analytics sont affichés pour les opportunités ayant une attribution 24B.

## Dégradation contrôlée

- aucune sélection : message invitant à sélectionner un objet ;
- objet Analytics sans opportunité : inspection de l'objet sans requête Decision Intelligence ;
- ancien run sans sidecar 24C : message d'indisponibilité, aucun crash ;
- changement de rôle ou de campagne : sélection Analytics effacée ;
- panneau fermé : état conservé sans supprimer la sélection.

## Tests ajoutés

- campagne normale : présence obligatoire des six sidecars ;
- garde d'architecture : post-run branché au dashboard, jamais aux GET ;
- garde d'isolation : aucun rerun Scanner / agents / Risk / PAPER ;
- store frontend : synchronisation sélection / opportunité / ouverture Inspector ;
- tests 24C.1 et 24C.2 existants conservés.

## Invariants

- aucune mutation de Scanner ;
- aucune mutation des agents ;
- aucune mutation du Risk Engine ;
- aucune mutation du PaperTradingPipeline ;
- aucun impact LIVE ;
- aucun lazy-compute dans les GET ;
- aucune rétroaction Analytics vers la décision.
