# Batch 23A.3 — Funnel Outcome Attribution

Baseline de départ : `b78266efe5c0bf203d75348907cac5000472e9c6`.

## Objectif

Croiser les métadonnées du Decision Funnel au niveau de chaque `CandidateOpportunity` avec les Forward Outcomes Batch 23A.2.

Le rapport répond de manière descriptive à des questions comme :

- que deviennent les opportunités terminées `NO_TRADE` ?
- que deviennent les propositions `RISK_REJECTED` ?
- quels reason codes Risk sont associés à quelles distributions H1/H3/H5/H10/H20 ?
- les opportunités analysées LONG/SHORT évoluent-elles ensuite dans la direction proposée ?
- quels triggers, régimes, décisions Compute Gate ou sélections d'agents sont associés aux distributions observées ?

Aucun groupe n'est classé « bon » ou « mauvais » automatiquement.

## Dimensions

Groupes produits :

- statut terminal PAPER ;
- régime de marché ;
- trigger Scanner ;
- reason Compute Gate ;
- décision Professor PLAN ;
- agent sélectionné ;
- échec orchestration ;
- direction Professor FINAL ;
- side de `TradeProposal` ;
- statut Risk ;
- reason code Risk ;
- échec Paper Pipeline.

Les dimensions `SCANNER_TRIGGER`, `SELECTED_AGENT` et `RISK_REASON` sont multi-valuées : une opportunité peut appartenir à plusieurs groupes. Les comptes de groupes ne doivent donc pas être additionnés comme s'ils étaient exclusifs.

## Statistiques par horizon

Pour chaque groupe et horizon :

- nombre total d'opportunités ;
- horizons complets / incomplets ;
- moyenne et médiane du rendement brut ;
- compte positif / négatif / flat ;
- moyenne et médiane max-upside / max-downside ;
- lorsque LONG/SHORT existe : rendement directionnel, excursion favorable et excursion adverse.

Direction :

1. `TradeProposal.side` si disponible ;
2. sinon Professor FINAL `LONG` / `SHORT` ;
3. sinon aucune métrique directionnelle.

Aucun seuil de rentabilité ou de « bonne opportunité » n'est inventé.

## Limite Scanner explicite

Batch 23A.2 produit des outcomes uniquement pour les `CandidateOpportunity`.

Par conséquent Batch 23A.3 **ne permet pas encore** d'évaluer :

- `SCANNER:NO_TRIGGER` ;
- `SCANNER:TRIGGER_BELOW_CANDIDATE_THRESHOLD`.

Le rapport publie explicitement :

- `scanner_no_trigger_outcomes_available = false` ;
- `scanner_below_candidate_threshold_outcomes_available = false`.

Cela empêche d'utiliser 23A.3 comme justification pour modifier le seuil Scanner.

## Frontière causale

Le rapport est construit après :

```text
Historical Replay
→ Evaluation
→ Decision Funnel
→ Forward Outcomes
→ Funnel Outcome Attribution
```

Il ne :

- modifie aucun `DecisionContext` ;
- modifie aucun `BacktestConfig` / `run_id` ;
- déclenche aucun Scanner/LLM/Risk/broker ;
- modifie aucun fingerprint business existant ;
- franchit aucune frontière DESIGN / VALIDATION / OOS.

## Export

Chaque période ajoute :

- `design-funnel-outcome-attribution.json` ;
- `validation-funnel-outcome-attribution.json` ;
- `oos-funnel-outcome-attribution.json`.
