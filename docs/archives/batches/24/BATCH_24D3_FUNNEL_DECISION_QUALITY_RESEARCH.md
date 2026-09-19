# Batch 24D.3 — Funnel Decision Quality Research

## Statut et baseline

Baseline d’entrée auditée :

```text
repository: Ax-07/Money-Heist
branch: main
commit: a50ac97ec7fc9ecf91ee7c3db3f6595ff400e829
message: feat(research): add scanner filtering quality analysis
```

24D.3 est **POST-HOC / READ-ONLY / RESEARCH-ONLY / DETERMINISTIC / NO TRADING AUTHORITY**.
Il consomme exclusivement le `DecisionQualityResearchBundle` 24D.1 et le
`FunnelStageAnalyticsAttributionSet` 24B.4. Il ne recalcule ni le funnel ni les Forward Outcomes.

## Audit des contrats réels

`FunnelStage` contient exactement :

```text
COMPUTE_GATE
PROFESSOR_PLAN
SPECIALIST
PALERMO
PROFESSOR_FINAL
TRADE_PROPOSAL
RISK
PAPER
```

La projection 24B.4 fournit pour les stages fixes une ligne par Candidate/Decision Intelligence
record. `SPECIALIST` est multi-instance et n’existe que pour une instance réellement atteinte ou
tentée. L’ordre canonique est celui de 24B.4 (`stage_order`, `stage_instance_order`).

Les résultats sont projetés depuis les faits métier canoniques, sans enum inventé :

```text
COMPUTE_GATE      -> ComputeGateProjection.level
PROFESSOR_PLAN    -> ProfessorPlanProjection.decision
SPECIALIST        -> SpecialistAnalysisProjection.stance
PALERMO           -> PalermoProjection.verdict
PROFESSOR_FINAL   -> ProfessorFinalProjection.direction
TRADE_PROPOSAL    -> TradeProposalProjection.side
RISK               -> RiskProjection.status
PAPER              -> BrokerOrder.status / failure.code / pipeline status
```

Les valeurs exactes restent donc celles réellement produites par les contrats amont. 24D.3 ne
réencode pas une taxonomie parallèle. Les exemples documentés (`CLEAR/CAUTION/REJECT`,
`LONG/SHORT/NO_TRADE`, `APPROVED/RESIZED/REJECTED`) ne deviennent des cohortes que lorsqu’ils
sont effectivement présents dans les records.

## Causalité locale par stage

Une information downstream ne peut jamais définir une cohorte causale d’un stage antérieur.
La frontière v1 est :

```text
Compute Gate      -> directionless
Professor PLAN    -> directionless
Specialists       -> directionless
Palermo           -> directionless
Professor FINAL   -> direction-aware si FINAL = LONG/SHORT
TradeProposal     -> direction-aware si cohérent avec FINAL
Risk              -> direction-aware car FINAL/Proposal précèdent Risk
PAPER             -> direction-aware car FINAL/Proposal précèdent PAPER
```

La direction FINAL n’est donc jamais injectée dans les descriptors de Compute Gate, PLAN,
Specialists ou Palermo. Une modification ultérieure de FINAL ne change pas l’appartenance à leurs
cohortes.

## Directionless outcome metrics

Pour chaque horizon canonique H1/H3/H5/H10/H20 :

- coverage outcome disponible/manquant ;
- complete/incomplete et raisons `GAP`, `PERIOD_END`, `GAP_AND_PERIOD_END` ;
- moyenne/médiane du `return_pct` brut ;
- comptes positif/négatif/flat ;
- moyenne/médiane `max_upside_pct` ;
- moyenne/médiane `max_downside_pct` ;
- moyenne/médiane de `max(abs(max_upside_pct), abs(max_downside_pct))` ;
- comptes `MAX_UPSIDE`, `MAX_DOWNSIDE`, `SAME_CANDLE`.

Un horizon incomplet reste dans le coverage mais ne publie aucune statistique de prix. Aucune
imputation à zéro n’est autorisée.

## Direction-aligned metrics

Uniquement avec une direction canonique explicite `LONG` ou `SHORT` et un horizon complet :

```text
LONG:
  directional_return_pct = raw return_pct
  favorable_excursion_pct = max_upside_pct
  adverse_excursion_pct = abs(max_downside_pct)

SHORT:
  directional_return_pct = -raw return_pct
  favorable_excursion_pct = abs(max_downside_pct)
  adverse_excursion_pct = max_upside_pct
```

Le first-hit est réaligné ainsi :

```text
LONG:  MAX_UPSIDE -> FAVORABLE ; MAX_DOWNSIDE -> ADVERSE
SHORT: MAX_DOWNSIDE -> FAVORABLE ; MAX_UPSIDE -> ADVERSE
SAME_CANDLE -> SAME_CANDLE
```

`NO_TRADE`, FINAL absent et FINAL failed n’ont aucune direction.

**Direction-aligned future movement != trade P&L.** Le Forward Outcome part du `reference_close`
à T ; il ne simule ni fill, ni fees, ni slippage, ni stop/target, ni taille. Un mouvement favorable
après `Risk REJECTED` ne prouve donc pas qu’un trade counterfactual aurait été profitable.

Le `first_hit` Forward Outcome compare le temps du maximum upside au temps du maximum downside.
Il ne signifie pas « target avant stop ». `SAME_CANDLE` conserve explicitement l’ambiguïté intrabar.

## Dimensions v1

```text
STAGE_REACHABILITY
STAGE_RESULT
STAGE_FAILURE
SPECIALIST_AGENT
SPECIALIST_STANCE
STAGE_REASON             (multi-valued)
PLAN_SELECTED_AGENT_COUNT
```

`STAGE_RESULT` couvre génériquement Compute Gate, PLAN, Palermo, FINAL, TradeProposal, Risk et
PAPER sans dupliquer des dimensions synonymes. `SPECIALIST_AGENT` et `SPECIALIST_STANCE` restent
des cohortes descriptives, sans ranking. `STAGE_REASON` est explicitement multi-valué et n’obéit pas
à une conservation par somme de groupes.

## Coverage

Le report expose :

- candidates avec/sans Forward Outcome ;
- candidates avec/sans Analytics match ;
- par stage : candidate_count, record_count, reached/not_reached, failure_count, coverage outcome,
  candidates_with_records et unique_agents.

Pour les stages fixes, 24B.4 garantit la conservation **par DecisionIntelligenceRecord**, pas par
Candidate 24D.1 lorsque la jointure Decision Intelligence est absente. Une Candidate avec
`causal.decision = None` reste donc dans le coverage global sans stage record ; une Candidate qui
possède une référence Decision Intelligence mais perd un stage fixe est fail-closed. Pour
`SPECIALIST`, le nombre de runs peut dépasser le nombre de Candidates.

## Cohérence de direction

La source canonique est `PROFESSOR_FINAL`. Si un `TradeProposal` est présent, son `side` doit être
`LONG/SHORT` et égal au FINAL ; sinon le builder échoue. `RiskInput.side` n’est pas promu comme
nouvelle vérité directionnelle.

## Contrasts v1

Ils sont produits seulement lorsque les deux cohortes observées existent :

```text
PALERMO: CLEAR vs CAUTION ; CLEAR vs REJECT ; CAUTION vs REJECT
FINAL:   LONG vs SHORT ; LONG vs NO_TRADE ; SHORT vs NO_TRADE
RISK:    APPROVED vs RESIZED ; APPROVED vs REJECTED ; RESIZED vs REJECTED
```

Les contrasts publient uniquement des deltas descriptifs `left - right`, avec tailles d’échantillon
et coverage. Les deltas directionnels ne sont disponibles que lorsque les deux côtés possèdent des
métriques directionnelles. Aucun `winner`, score qualité, ranking, p-value ou claim causal.

## Identité et déterminisme

`report_id` dépend de l’identité de recherche, des fingerprints du bundle et du stage-set et de la
policy `funnel-decision-quality-descriptive-v1`. Le report fingerprint couvre sources, coverage,
cohort fingerprints et contrasts. Les cohortes sont triées par ordre canonique de stage, ordre de
dimension et clé stable. Aucun wall-clock ne participe à l’identité.

## DESIGN / VALIDATION / OOS

Le `period_role` est hérité du bundle 24D.1. Aucune agrégation cross-role n’est effectuée. Observer
OOS n’autorise pas à tuner puis à présenter le même OOS comme intact.

## Hors scope

- persistance automatique 24D ;
- endpoint ou frontend ;
- recommendations/tuning ;
- ranking agent ;
- mining de seuils confidence/severity/RR ;
- simulateur counterfactual stop/target/P&L ;
- modification Scanner/Compute Gate/DecisionContext/Agents/Palermo/Risk/PAPER/LIVE.

Ces sujets restent hors de 24D.3 ; 24D.4 est le futur `Research Reports & Evidence Explorer`.
