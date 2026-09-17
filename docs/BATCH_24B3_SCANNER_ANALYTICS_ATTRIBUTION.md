# Batch 24B.3 — Scanner ↔ Analytics Attribution Layer

## Objectif

24B.3 ajoute une couche d'attribution **post-hoc, read-only et causale** entre chaque évaluation du Scanner produite par Historical Replay et le `AnalyticsSnapshot` exact correspondant au même instant de décision.

Le batch ne relance pas le Scanner, ne recalcule pas les features, n'influence aucune décision et n'introduit aucune autorité Analytics dans Scanner, Agents, Risk, PAPER ou LIVE.

## Identité Scanner canonique

L'identité d'une évaluation Scanner reste l'identité déjà utilisée par 23A.4 :

```text
scanner_evaluation_id == FeatureSnapshot.snapshot_id
```

Aucun nouvel identifiant métier n'est créé pour représenter le même événement.

## Classification State@T

La primitive neutre `app.evaluation.scanner_observations` porte les trois états déjà définis par 23A.4 :

- `NO_TRIGGER` ;
- `TRIGGER_BELOW_CANDIDATE_THRESHOLD` ;
- `CANDIDATE_OPPORTUNITY`.

`scanner_forward_outcomes` réutilise cette enum afin d'éviter deux sources de vérité.

## Matching Analytics

24B.3 réutilise la même policy que 24B.1 :

```text
opportunity-analytics-exact-v1
```

La résolution est factorisée dans `AnalyticsSnapshotResolver`. Le matching reste strictement exact sur la provenance et le temps : BacktestRun, dataset id/version/SHA/source, system, symbol, source timeframe, decision timeframe, MTF policy, `as_of` et `source_cursor_fingerprint`.

Il n'existe aucun fallback vers un snapshot précédent, futur ou "le plus proche".

## Provenance causale

Le `source_cursor_fingerprint` vient exclusivement du replay (`HistoricalReplayPoint.mtf_cursor_fingerprint`) ou de la même provenance portée par `DecisionContext` quand elle est disponible. Il n'est jamais reconstruit à partir des données futures.

Une provenance absente ou incohérente produit un statut explicite et ne fabrique pas de match.

## Contrats publics

Le batch ajoute :

- `ScannerObservation` ;
- `AnalyticsSnapshotResolver` ;
- `ScannerAnalyticsAttributionRecord` ;
- `ScannerAnalyticsAttributionSet` ;
- `build_scanner_analytics_attribution`.

Chaque Scanner evaluation produit exactement un `ScannerAnalyticsAttributionRecord`, y compris lorsqu'aucune `CandidateOpportunity` n'est créée.

Pour les lignes `CANDIDATE_OPPORTUNITY`, le record peut référencer le `OpportunityAnalyticsLink` 24B.1 et le `DecisionIntelligenceRecord` 24B.2. Quand ces sidecars sont fournis, leur cohérence est validée ; ils ne sont jamais utilisés pour rematcher Analytics.

## Déterminisme

Les identités et fingerprints utilisent les helpers canoniques communs. À entrées identiques, l'ordre, les IDs, les fingerprints et le JSON Pydantic sont déterministes.

## Hors scope

24B.3 n'ajoute pas :

- d'indicateurs ou patterns supplémentaires ;
- de Forward Outcomes ;
- de tuning du Scanner ;
- de feedback Analytics vers les décisions ;
- de changement du `BacktestRun.run_id` ;
- de changement du business fingerprint historique ;
- d'API/UI ou de comportement LIVE.
