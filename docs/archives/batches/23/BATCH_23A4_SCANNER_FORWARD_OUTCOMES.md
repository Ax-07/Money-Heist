# Batch 23A.4 — Scanner Forward Outcomes

Baseline de départ : `42903cce9e694fdf1f23923fdba0708176e7775a`.

## Objectif

Étendre la couche de mesure causale **avant la création de `CandidateOpportunity`**.

Batch 23A.4 calcule des Forward Outcomes pour **chaque évaluation Scanner** déjà produite par Historical Replay, sans rappeler le Scanner et sans modifier ses seuils.

Trois classes exclusives :

1. `NO_TRIGGER`
2. `TRIGGER_BELOW_CANDIDATE_THRESHOLD`
3. `CANDIDATE_OPPORTUNITY`

La conservation imposée est :

```text
scanner_evaluations
=
NO_TRIGGER
+ TRIGGER_BELOW_CANDIDATE_THRESHOLD
+ CANDIDATE_OPPORTUNITY
```

Les compteurs doivent aussi correspondre exactement à Batch 23A.1 Decision Funnel.

## Pourquoi ce lot

Batch 23A.2 et 23A.3 commencent au `CandidateOpportunity`.

Ils peuvent expliquer ce qui se passe après la création du candidat, mais pas répondre à :

- les bougies sans trigger avaient-elles malgré tout de grands mouvements futurs ?
- les triggers sous le seuil candidat étaient-ils réellement moins intéressants ?
- les scores juste sous le seuil actuel ont-ils des distributions différentes ?
- certains triggers sont-ils associés à des outcomes futurs distincts ?

23A.4 rend ces questions mesurables **sans modifier le Scanner**.

## Données enregistrées par évaluation

- `scan_id` / `snapshot_id` ;
- timestamp ;
- close de référence ;
- classification ;
- score Scanner exact ;
- `min_priority_score` réellement utilisé ;
- marge `score - min_priority_score` ;
- triggers ;
- régime de marché ;
- `candidate_opportunity_id` éventuel ;
- H1 / H3 / H5 / H10 / H20.

Aucune bande de score arbitraire n'est créée.

Les agrégats sont disponibles par :

- classification ;
- score exact ;
- trigger ;
- régime de marché.

`TRIGGER` est une dimension multi-valuée : une même évaluation peut appartenir à plusieurs groupes trigger.

## Outcomes

Le calcul réutilise **le moteur Batch 23A.2** :

- mêmes horizons dans le timeframe de décision ;
- même close de référence ;
- même rendement close-to-close ;
- même max-upside / max-downside ;
- même first-hit ;
- mêmes règles de gap et de frontière DESIGN / VALIDATION / OOS ;
- aucune métrique partielle sur horizon incomplet.

Le Scanner reste directionless. Les statistiques 23A.4 sont donc brutes et ne transforment pas un mouvement haussier ou baissier en recommandation LONG/SHORT.

## Invariants

Le rapport échoue si :

- le nombre de records diffère de `DecisionFunnel.scanner_evaluations` ;
- `NO_TRIGGER` diffère de `DecisionFunnel.scanner_no_trigger` ;
- `CANDIDATE_OPPORTUNITY` diffère de `DecisionFunnel.candidate_opportunities` ;
- les triggers sous seuil ne correspondent pas à `scanner_triggered - candidate_opportunities` ;
- un candidat a un score différent du `ScanResult` ;
- le `scanner_version` ne correspond pas au `BacktestConfig` ;
- les règles score/seuil ne correspondent pas à la classification observée.

## Frontière causale

Le rapport est calculé post-hoc :

```text
Historical Replay
→ Evaluation
→ Decision Funnel
→ Forward Outcomes candidats
→ Funnel Outcome Attribution
→ Scanner Forward Outcomes
```

Aucun résultat 23A.4 :

- n'entre dans `DecisionContext` ;
- n'entre dans le Scanner ;
- ne change un prompt ;
- ne change Risk ;
- ne change le broker ;
- ne change `BacktestConfig`, `run_id` ou le fingerprint business.

## Export

Chaque période ajoute :

- `design-scanner-forward-outcomes.json`
- `validation-scanner-forward-outcomes.json`
- `oos-scanner-forward-outcomes.json`

Ce lot permet enfin de comparer quantitativement le comportement post-hoc des évaluations **avant et après le seuil candidat**, avant toute décision éventuelle de tuning.
