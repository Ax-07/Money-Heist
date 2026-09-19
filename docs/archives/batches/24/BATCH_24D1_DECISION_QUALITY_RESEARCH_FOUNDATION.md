# Batch 24D.1 â€” Decision Quality Research Foundation & Outcome Join

**Baseline auditÃ©e :** `a010155337a446bcbd06ded32667ea667b1512d7`
**Branche :** `main`
**Statut :** fondation domaine/evaluation, read-only, post-hoc, research-only

## 1. Baseline et audit prÃ©alable

Le `HEAD` GitHub de `Ax-07/Money-Heist` est exactement la baseline demandÃ©e :
`a010155337a446bcbd06ded32667ea667b1512d7`. La comparaison
`a010155...main` est `identical`, `ahead_by=0`, `behind_by=0`.

Le code auditÃ© confirme les contrats suivants.

### 23A.2 â€” Forward Outcomes

- `ForwardOutcomeReport.schema_version = money-heist.forward-outcomes.v1` ;
- `policy_version = money-heist.forward-outcomes.close-ohlc.v1` ;
- horizons canoniques : `H1/H3/H5/H10/H20` ;
- identitÃ© Candidate : `opportunity_id` ;
- prix de rÃ©fÃ©rence : `reference_close` Ã  T ;
- `return_pct` = variation du close final de l'horizon par rapport Ã  `reference_close` ;
- `max_upside_pct` et `max_downside_pct` utilisent respectivement le high maximal et le low minimal futurs ;
- un horizon incomplet ne publie **aucune** mÃ©trique de prix partielle ;
- raisons incomplÃ¨tes : `GAP`, `PERIOD_END`, `GAP_AND_PERIOD_END`.

Ces valeurs dÃ©crivent un **future price outcome**. Elles ne reprÃ©sentent pas un P&L de trade hypothÃ©tique.

### 23A.3 â€” Funnel Outcome Attribution

- schema : `money-heist.funnel-outcome-attribution.v1` ;
- policy : `money-heist.funnel-outcome-attribution.descriptive.v1` ;
- jointure exacte par `opportunity_id` ;
- validation de paritÃ© `observed_at`, `terminal_status`, direction Professor et side de proposition ;
- agrÃ©gation strictement descriptive ;
- la direction n'existe que si un `LONG/SHORT` canonique existe dÃ©jÃ  ; elle n'est jamais dÃ©duite du futur.

24D.1 n'utilise pas ce rapport comme seconde source de faits funnel : le `DecisionIntelligenceRecord` 24B.2 est dÃ©jÃ  la projection causale canonique.

### 23A.4 â€” Scanner Forward Outcomes

- schema : `money-heist.scanner-forward-outcomes.v1` ;
- policy : `money-heist.scanner-forward-outcomes.close-ohlc.v1` ;
- identitÃ© publiÃ©e : `scan_id` ;
- le moteur rÃ©utilise **directement** 23A.2, en projetant temporairement `scan_id` comme identitÃ© gÃ©nÃ©rique ;
- aucun second moteur de Forward Outcomes ;
- support explicite `NO_TRIGGER`, `TRIGGER_BELOW_CANDIDATE_THRESHOLD`, `CANDIDATE_OPPORTUNITY`.

### 24B.2 â€” Decision Intelligence

- schema record : `money-heist.decision-intelligence-record.v1` ;
- set : `money-heist.decision-intelligence-record-set.v1` ;
- policy : `decision-intelligence-projection-v1` ;
- identitÃ© Candidate : `opportunity_id` ;
- `record_id` et fingerprints dÃ©terministes via `stable_uuid` / `stable_digest` ;
- projection causale canonique Scanner â†’ Compute Gate â†’ PLAN â†’ Specialists â†’ Palermo â†’ FINAL â†’ TradeProposal â†’ Risk â†’ PAPER ;
- `AnalyticsRefProjection` conserve l'identitÃ© 24B.1 sans recalcul Analytics.

### 24B.3 â€” Scanner Analytics Attribution

- schema : `money-heist.scanner-analytics-attribution.v1` ;
- set : `money-heist.scanner-analytics-attribution-set.v1` ;
- projection : `scanner-analytics-attribution-v1` ;
- matching policy : `opportunity-analytics-exact-v1` ;
- identitÃ© Scanner canonique :

```text
scanner_evaluation_id == FeatureSnapshot.snapshot_id
```

23A.4 appelle cette mÃªme identitÃ© `scan_id`. 24D.1 exige donc :

```text
ScannerAnalyticsAttributionRecord.scanner_evaluation_id
== ScannerForwardOutcomeRecord.scan_id
```

sans nearest timestamp ni approximation.

### 24B.4 â€” Funnel Stage Analytics Attribution

- schema : `money-heist.funnel-stage-analytics-attribution.v1` ;
- set : `money-heist.funnel-stage-analytics-attribution-set.v1` ;
- policy : `funnel-stage-analytics-attribution-v1` ;
- rÃ©fÃ©rence le `DecisionIntelligenceRecord` et son fingerprint ;
- sÃ©pare `market_as_of` de `operational_at` ;
- ne back-propage jamais Analytics depuis une Ã©tape future.

24D.1 peut valider ce set lorsqu'il est fourni, mais ne le duplique pas dans les records de recherche.

### 24C â€” post-run et persistance

Le post-run courant construit automatiquement :

```text
24A Analytics
â†’ 24B.1 Opportunity links
â†’ 24B.2 Decision Intelligence
â†’ 24B.3 Scanner Attribution
â†’ 24B.4 Funnel Stage Attribution
â†’ 24C frontend projections
```

et persiste les projections frontend dans le sidecar existant. Les 23A Forward Outcomes sont construits plus tÃ´t dans l'exÃ©cution de rÃ´le et restent portÃ©s par l'objet d'exÃ©cution du Dashboard.

**DÃ©cision 24D.1 :** ne pas brancher la persistance research dans `app/dashboard/analytics_postrun.py` Ã  ce stade. Ce module est une frontiÃ¨re 24Aâ†’24Bâ†’24C orientÃ©e projection frontend ; y injecter 23A imposerait une nouvelle dÃ©pendance de l'orchestrateur Dashboard et figerait prÃ©maturÃ©ment le contrat de stockage 24D. Le bundle 24D.1 est sÃ©rialisable de faÃ§on canonique (`to_json`) et prÃªt pour un branchement post-run dÃ©diÃ© lorsque le contrat d'export/Explorer sera figÃ©. Aucun GET frontend ne dÃ©clenche de calcul research.

## 2. Cartographie des identitÃ©s

| Domaine | IdentitÃ© canonique / contrÃ´le 24D |
|---|---|
| Backtest | `BacktestRun.run_id` / `source_backtest_run_id` |
| PÃ©riode | `DESIGN`, `VALIDATION`, `OOS` via `analytics_period_role` |
| Dataset | `dataset_id`, `dataset_version`, `dataset_content_sha256`, `dataset_source` |
| Candidate | `opportunity_id` |
| Scanner | `scanner_evaluation_id == snapshot_id`, joint Ã  `ScannerForwardOutcomeRecord.scan_id` |
| Decision Intelligence | `record_id`, `record_fingerprint`, `opportunity_fingerprint` |
| Analytics run | `analytics_run_id` |
| Analytics snapshot | `analytics_snapshot_id`, `analytics_snapshot_fingerprint`, `analytics_as_of` |
| Forward Outcome Candidate | `ForwardOutcomeRecord.opportunity_id` |
| Forward Outcome Scanner | `ScannerForwardOutcomeRecord.scan_id` |
| Research run | dÃ©terministe depuis run + analytics run + rÃ´le + dataset + policy 24D + dÃ©finitions outcomes |

## 3. Cartographie des versions / fingerprints

24D.1 conserve explicitement :

- Decision Intelligence : `decision-intelligence-projection-v1` ;
- Scanner Analytics Attribution : `scanner-analytics-attribution-v1` ;
- Analytics exact-match : `opportunity-analytics-exact-v1` ;
- Forward Outcomes : `money-heist.forward-outcomes.close-ohlc.v1` ;
- Scanner Forward Outcomes : `money-heist.scanner-forward-outcomes.close-ohlc.v1` ;
- Decision Quality Research : `decision-quality-research-exact-join-v1`.

Le `causal_fingerprint` est indÃ©pendant du bloc post-hoc. Le `record_fingerprint` global inclut le fingerprint outcome canonique et change donc lorsque l'Ã©valuation future change, tandis que `record_id` et `causal_fingerprint` restent stables pour la mÃªme dÃ©cision Ã  T et le mÃªme research run.

## 4. DÃ©cisions d'architecture â€” questions avant code

1. **Candidate vs modÃ¨le gÃ©nÃ©rique :** deux modÃ¨les spÃ©cialisÃ©s. `CandidateResearchRecord` possÃ¨de un funnel dÃ©cisionnel ; `ScannerResearchRecord` supporte aussi les observations sans Candidate.
2. **Research run identity :** `source_backtest_run_id + analytics_run_id + period_role + dataset identity + research policy + outcome schema/policy/horizons`.
3. **Projection causale directe :** identitÃ© Scanner, classification/score/seuil/marge/triggers/rÃ©gime, refs Analytics ; pour Candidate, FINAL, Palermo, Risk et statuts pipeline sont projetÃ©s depuis 24B.2.
4. **Refs seulement :** Analytics riche, Contexts/Sequences, patterns/events/structure complets et Funnel Stage 24B.4 restent rÃ©fÃ©rencÃ©s par leurs artefacts canoniques ; aucune copie massive.
5. **Taxonomie join :** `MATCHED`, `MISSING_DECISION_INTELLIGENCE`, `MISSING_FORWARD_OUTCOME`, `MISSING_ANALYTICS`. Les contaminations globales `RUN/ROLE/DATASET/..._MISMATCH` sont des erreurs d'intÃ©gritÃ© fail-closed, pas des records valides.
6. **Horizons incomplets :** objets 23A conservÃ©s tels quels ; aucune mÃ©trique partielle, aucun zÃ©ro synthÃ©tique, aucun backfill.
7. **Persistance :** non branchÃ©e dans 24D.1 ; bundle canonique sÃ©rialisable, contrat de fichier Ã  figer avec le futur Explorer.
8. **Ordonnancement post-run :** lorsqu'il sera branchÃ©, uniquement aprÃ¨s 23A + 24A/24B ; jamais avant disponibilitÃ© des outcomes et attributions.
9. **DESIGN/VALIDATION/OOS :** un bundle = un seul rÃ´le. Un rÃ´le diffÃ©rent de `ScannerAnalyticsAttributionSet.analytics_period_role` est rejetÃ©.
10. **Architecture guards :** interdiction de dÃ©pendance 24D depuis `app.analytics`, Scanner, agents, Risk, PAPER et LIVE ; 24B reste indÃ©pendant de Forward Outcomes et de 24D.

## 5. SÃ©paration structurelle

Chaque record est divisÃ© en deux blocs explicites :

```text
causal
  informations disponibles / persistÃ©es Ã  T

posthoc
  future_outcome canonique 23A, observÃ© aprÃ¨s T
```

Interdictions du batch :

```text
future price outcome != hypothetical trade P&L
NO_TRIGGER + future move != automatically missed opportunity
NO_TRADE + adverse move != automatically protective decision
```

Aucun label `GOOD/BAD`, aucune optimisation de threshold, aucun classement d'agent, aucun tuning de prompt, aucune simulation contrefactuelle.

## 6. Join exact et couverture

### Candidate

L'univers Candidate provient des Scanner attributions classÃ©es `CANDIDATE_OPPORTUNITY`. Ceci permet de conserver le sujet mÃªme si son `DecisionIntelligenceRecord` manque.

Jointures :

```text
candidate_opportunity_id
â†’ DecisionIntelligenceRecord.opportunity_id
â†’ ForwardOutcomeRecord.opportunity_id
```

### Scanner

L'univers Scanner est l'intÃ©gralitÃ© de `ScannerAnalyticsAttributionSet.records`, donc `NO_TRIGGER` et `TRIGGER_BELOW_CANDIDATE_THRESHOLD` ne sont jamais perdus.

Jointure :

```text
scanner_evaluation_id
== FeatureSnapshot.snapshot_id
== ScannerForwardOutcomeRecord.scan_id
```

Les compteurs de coverage sont des mÃ©triques d'intÃ©gritÃ© uniquement, jamais des mÃ©triques de performance.

## 7. DÃ©terminisme

Ã€ artefacts identiques :

- mÃªme `research_run_id` ;
- mÃªmes record IDs ;
- mÃªme ordre Candidate `(observed_at, opportunity_id, record_id)` ;
- mÃªme ordre Scanner `(observed_at, scan_id, record_id)` ;
- mÃªmes fingerprints ;
- mÃªme `bundle_fingerprint`.

Aucun timestamp wall-clock n'entre dans les identitÃ©s.

## 8. Delta 24D.1

### CrÃ©Ã©s

```text
app/evaluation/decision_quality/__init__.py
app/evaluation/decision_quality/models.py
app/evaluation/decision_quality/join.py
tests/evaluation/test_decision_quality.py
tests/evaluation/test_decision_quality_architecture.py
docs/BATCH_24D1_DECISION_QUALITY_RESEARCH_FOUNDATION.md
CHANGELOG_BATCH_24D1.md
```

### ModifiÃ©s

Aucun fichier runtime existant. Cette dÃ©cision garde 24D extÃ©rieure aux moteurs existants et Ã©vite tout feedback comportemental.

## 9. Roadmap 24D retenue

```text
24D.1 â€” Decision Quality Research Foundation & Outcome Join
24D.2 â€” Scanner Filtering Quality Research
24D.3 â€” Funnel Decision Quality Research
24D.4 â€” Research Reports & Evidence Explorer
```

24D.2/24D.3/24D.4 restent hors scope du prÃ©sent batch.
