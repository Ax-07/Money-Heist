# Money Heist — Batch 24B.1 Opportunity ↔ Analytics Linking

**Baseline auditée :** `6d67e3f25a6c95f23552a5f4f025bd1b4d29a26c`  
**Policy :** `opportunity-analytics-exact-v1`  
**Autorité :** observation-only, read-only, post-hoc

## 1. Objectif

24B.1 prouve qu'une `CandidateOpportunity` du replay et un `AnalyticsSnapshot` décrivent le
même préfixe historique. Le batch n'ajoute aucune donnée Analytics à `CandidateOpportunity`, ne
modifie pas `DecisionContextV1` et ne change aucune sortie métier.

## 2. Source décisionnelle

Le Scanner actuel crée `CandidateOpportunity.created_at` depuis
`FeatureSnapshot.observed_at`. Le replay conserve en plus, sur chaque `HistoricalReplayPoint`,
le `mtf_cursor_fingerprint` correspondant à l'univers causal visible à cet instant.

24B.1 adapte donc les artefacts existants vers :

```text
DecisionObservationKey
  source_backtest_run_id
  dataset_id / version / content_sha256 / source
  system_id
  symbol
  source_timeframe
  decision_timeframe
  observed_at
  mtf_policy_version
  source_cursor_fingerprint
  feature_snapshot_id
  feature_version
  scanner_version
```

Le `DecisionContext` est facultatif. S'il existe, son `as_of`, son symbole, son primary timeframe
et `market.source_cursor_fingerprint` sont validés contre le replay, puis seuls
`context_id/context_fingerprint` sont conservés dans le sidecar.

## 3. Cible Analytics

Le linker consomme les `AnalyticsLabRun` et `AnalyticsSnapshot` canoniques de 24A. Il ne crée
aucun second snapshot et ne recalcule aucun composant Analytics.

`AnalyticsSnapshotIndex` est volontairement distinct de `AnalyticsObservationIndex` : ce
dernier sert aux recherches causales 24A.7 et possède des opérations « latest at or before ».
24B.1 exige au contraire un lookup exact.

Clé exacte :

```text
(symbol, decision_timeframe, as_of)
```

à l'intérieur d'un `analytics_run_id` explicitement fourni.

## 4. Policy de matching v1

Avant de considérer un snapshot comme `MATCHED`, le linker vérifie dans cet ordre :

```text
source_backtest_run_id
canonical dataset id/version/SHA/source
system_id
symbol
source timeframe
decision timeframe
MTF policy
Analytics run period / as_of
source cursor availability
exact snapshot key
unique candidate
source cursor fingerprint equality
```

Aucun fallback vers le snapshot précédent, futur ou « le plus proche » n'existe.

## 5. Statuts

La v1 expose notamment :

```text
MATCHED
MISSING_ANALYTICS_SNAPSHOT
AMBIGUOUS_ANALYTICS_SNAPSHOT
SOURCE_PROVENANCE_INCOMPLETE
SOURCE_BACKTEST_RUN_MISMATCH
DATASET_MISMATCH
SYSTEM_MISMATCH
SYMBOL_MISMATCH
SOURCE_TIMEFRAME_MISMATCH
TIMEFRAME_MISMATCH
AS_OF_MISMATCH
MTF_POLICY_MISMATCH
CURSOR_FINGERPRINT_MISMATCH
```

Les diagnostics sont descriptifs. Ils ne déclenchent aucun recalcul ni aucune action de trading.

## 6. Identités déterministes

`OpportunityAnalyticsLink.link_id` est dérivé de l'identité stable du source BacktestRun, du
run Analytics explicitement choisi, de l'opportunité, du snapshot résolu lorsque disponible et
de la policy. `link_fingerprint` inclut en plus le statut, la provenance complète et les
diagnostics.

`AnalyticsSnapshotRef.analytics_snapshot_fingerprint` est le SHA-256 canonique du
`AnalyticsSnapshot.identity_payload()` ; le `snapshot_id` canonique 24A reste inchangé.

Un `OpportunityAnalyticsLinkSet` trie les liens de manière stable et publie un
`summary_fingerprint` déterministe ainsi que les compteurs de couverture.

## 7. Isolation

```text
Decision / Replay artifacts ───────┐
                                   │ read-only
                                   v
                         Analytics Attribution
                                   ^
                                   │ read-only
Analytics Core artifacts ──────────┘
```

Interdictions :
- `app.analytics` n'importe pas la couche d'attribution ;
- Scanner/DecisionContext/Agents/Risk/PAPER/LIVE n'importent pas la couche d'attribution ;
- `BacktestRun`, `HistoricalReplayRunner` et `reproducibility.py` n'importent pas la couche ;
- l'attribution n'importe ni Forward Outcomes, ni agents, ni Risk, ni brokers.

## 8. Hors scope

24B.1 ne réalise pas :
- `DecisionIntelligenceRecord` (24B.2) ;
- attribution complète de chaque Scanner evaluation (24B.3) ;
- attribution des étapes du funnel (24B.4) ;
- Forward Outcomes ;
- API/UI Decision Intelligence ;
- tuning automatique.

## 9. Validation attendue

Les tests ciblés couvrent : exact-as-of, absence de nearest match, symbol/timeframe/dataset/MTF
policy/cursor mismatches, snapshot manquant, ambiguïté, déterminisme ID/fingerprint/ordre,
Analytics run distinct, opportunité avec/sans DecisionContext, causalité face aux snapshots
futurs, isolation du business fingerprint et guards d'imports.
