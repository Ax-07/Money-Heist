# Batch 24A.6 — Pattern Calibration & Pivot-Source Diagnostics

## Statut

Couche Analytics **READ-ONLY / OBSERVATION-ONLY / RESEARCH-ONLY**. Elle ne possède aucune autorité Scanner, Agents, Risk, PAPER ou LIVE.

## Principe

24A.6 rend le moteur Patterns 24A.5 observable sans créer un second moteur. Les mêmes règles, seuils, lifecycle et policy intrabar restent canoniques. La calibration compare des sources de pivots à règles constantes et n'utilise aucun Forward Outcome.

```text
MONEY_HEIST_STRUCTURE ─┐
                       ├─> PatternPivot -> Pattern Engine 24A.5 -> diagnostics
CAUSAL_ZIGZAG ─────────┘                              -> accepted/rejected
                                                      -> source summaries
```

## Candidat

Un candidat est une fenêtre stable de pivots alternés : 3 pivots pour double top/bottom, 5 pour H&S/inverse H&S, 6 pour les géométries. Son identité dépend de la famille/type, source, IDs/fingerprints des pivots, symbole/timeframe et version du Pattern Registry. Elle ne dépend pas de `as_of`, P&L, Forward Outcome ou décision de trading.

`accepted=true` signifie que la géométrie passe et que l'occurrence est conservée après déduplication canonique. Le lifecycle `FORMING/CONFIRMED/FAILED/INVALIDATED` reste distinct : un pattern `FORMING` peut donc être un candidat accepté.

## Rejets et règles

Chaque garde-fou évalué produit `rule_id`, `pass/fail`, valeurs observées et contraintes requises. Les raisons couvrent spacing, similarité/profondeur, prior trend, symétrie H&S, durée/fit/largeur/classification/apex et suppression de doublon. Toutes les raisons déterministes sont conservées dans l'ordre des règles.

`BREAKOUT_NOT_CONFIRMED` n'est pas une raison de rejet 24A.6 : le breakout appartient au lifecycle 24A.5, pas à l'acceptation géométrique.

## Sources de pivots

`CAUSAL_ZIGZAG` réutilise l'adapter 24A.5. `MONEY_HEIST_STRUCTURE` utilise un adapter Analytics séparé qui reproduit les pivots stricts `pivot_span` sans modifier `app/market/structure.py`. Le pivot géométrique à `i` n'est disponible qu'après fermeture des `pivot_span` candles de droite ; son `confirmed_at` est causal.

## Identités

```text
BacktestRun
  -> AnalyticsLabRun
      -> PatternCalibrationRun
```

Changer la version de calibration change `calibration_run_id`, jamais `BacktestRun.run_id` ni son business fingerprint.

## Rapports

Par source : pivots confirmés, candidats, acceptés, rejetés, ratios internes de détection, comptes par pattern et distribution des raisons de rejet. Une comparaison exige explicitement la même version du Pattern Registry.

`acceptance_ratio` est un ratio interne au détecteur, **pas** un win rate de trading.

Aucun ranking, winner, score global ou optimisation de seuil n'est produit.

## DESIGN / VALIDATION / OOS

Le `period_role` de l'AnalyticsLabRun est conservé. Les rapports de rôles différents ne sont pas fusionnés implicitement. DESIGN peut guider une décision humaine future ; VALIDATION/OOS ne modifient jamais automatiquement le registry.

## Interdictions

- aucun import Forward Outcomes ;
- aucun P&L/future return pour accepter ou rejeter ;
- aucun auto-tuning ;
- aucun changement des seuils 24A.5 ;
- aucun frontend ;
- aucun Context/Sequence 24A.7.
