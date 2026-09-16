# Batch 23A.2 — Forward Outcomes

Baseline de départ : `096f5e5f4c16b47f5e9926065c3c4206dfc19c17`.

## Objectif

Mesurer **post-hoc** le devenir du marché après chaque `CandidateOpportunity`, quelle que soit sa terminaison (`NO_ANALYSIS`, `NO_TRADE`, `RISK_REJECTED`, `EXECUTED`, ou autre statut réellement émis).

Batch 23A.2 n'ajoute aucun signal et ne modifie aucune décision.

## Horizons

Horizons par défaut :

- H1 ;
- H3 ;
- H5 ;
- H10 ;
- H20.

`Hn` signifie **n bougies du timeframe de décision** après l'opportunité. Dans un replay source `1m` avec décision `1h`, H1 signifie donc une bougie `1h`, pas une minute.

## Référence et métriques

Prix de référence : `FeatureSnapshot.close` observé lors de l'opportunité.

Pour un horizon complet :

- `return_pct` : rendement close-to-close signé ;
- `max_upside_pct` : maximum du `high` par rapport au prix de référence, signé ;
- `max_downside_pct` : minimum du `low` par rapport au prix de référence, signé ;
- `max_upside_at` / `max_downside_at` ;
- `first_hit` : indique laquelle des deux extrêmes finales de l'horizon a été atteinte la première ; `SAME_CANDLE` si les deux extrêmes sont dans la même bougie.

Aucun seuil de profit/stop arbitraire n'est introduit.

## Horizons incomplets

Un horizon n'est complet que si toutes les bougies attendues existent.

Deux causes sont séparées :

- `GAP` : bougie attendue absente avant la fin de la période ;
- `PERIOD_END` : l'horizon dépasse la frontière DESIGN / VALIDATION / OOS ;
- `GAP_AND_PERIOD_END` : combinaison des deux.

Un horizon incomplet **ne publie pas de métriques partielles**. Cela évite de comparer un H20 complet à un H20 calculé sur seulement 7 bougies.

## Frontière causale

Le calcul est exécuté uniquement **après** la fin du Historical Replay.

`ForwardOutcomeReport` :

- n'entre jamais dans `DecisionContext` ;
- ne modifie pas `BacktestConfig` ;
- ne modifie pas `run_id` ;
- ne déclenche aucun Scanner, agent, Risk Engine ou broker ;
- n'est pas inclus dans le fingerprint business existant ;
- ne traverse pas la frontière de période du run.

## Exports

Pour chaque split :

- `design-forward-outcomes.json` ;
- `validation-forward-outcomes.json` ;
- `oos-forward-outcomes.json`.

Les records conservent notamment :

- `opportunity_id` ;
- `snapshot_id` ;
- statut terminal du pipeline ;
- direction Professor éventuelle ;
- side de `TradeProposal` éventuel ;
- timeframe source et timeframe de décision au niveau du rapport ;
- provenance dataset via id/version/SHA/source.
