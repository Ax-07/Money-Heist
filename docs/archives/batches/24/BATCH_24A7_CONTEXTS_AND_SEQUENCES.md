# Batch 24A.7 — Causal Contexts & Sequences

## Statut

Implémentation candidate à valider sur la baseline `0dc8200025ae7ca43964cadc04dff6e1ba1ac065`.

## Frontière constitutionnelle

Les Contexts et Sequences sont des artefacts **Analytics Research** : read-only, observation-only, déterministes, causaux et replay-safe. Un `AnalyticsContextDefinition` n'est jamais un `DecisionContextV1`. Le package `app.analytics.research` n'importe ni Scanner, ni agents, ni Risk/PAPER/LIVE, ni Forward Outcomes.

`AnalyticsLabRun` conserve l'identité des calculs Analytics canoniques. Une hypothèse de recherche est évaluée par un `AnalyticsResearchRun` séparé, qui référence le `analytics_run_id` de base et la révision immuable de la définition. Modifier une définition ne modifie donc pas `BacktestRun.run_id`, le business fingerprint ou l'identité Analytics de base.

## Observation Index

`AnalyticsObservationIndex` agrège uniquement des artefacts déjà calculés :

- `AnalyticsIndicatorSnapshot` (`snapshot.as_of <= T`) ;
- `TechnicalEventObservation` (`available_at <= T`) ;
- `AnalyticsMarketStructureObservation` (`as_of <= T`) ;
- `CausalZigZagPivot` (`confirmed_at <= T`) ;
- `PatternOccurrence` et ses `PatternTransition` (`available_at <= T`).

`with_as_of(T)` ne peut que réduire une vue existante. Il ne peut jamais révéler une observation postérieure au cutoff de l'index.

## Context DSL v1

### Anchors

- `TECHNICAL_EVENT` : `anchor_at = available_at` ;
- `PATTERN_TRANSITION` : `anchor_at = transition.available_at` ;
- `ZIGZAG_PIVOT` : `anchor_at = confirmed_at`, jamais `pivot_at`.

Indicateurs et structure ne sont pas des anchors v1 : ils sont des états évalués comme conditions.

### Conditions

- `INDICATOR` : opérateurs `GT`, `GTE`, `LT`, `LTE`, `EQ`, `BETWEEN` ; `BETWEEN` inclut les deux bornes ; warmup/inconnu = no-match ;
- `TECHNICAL_EVENT` : événement exact à l'anchor ou dans les N barres précédentes ;
- `PATTERN_TRANSITION` : transition observée ou `CURRENT_STATUS` reconstruit uniquement depuis les transitions visibles ;
- `STRUCTURE` : `swing_structure`, `breakout_state` ou `range_location` depuis la projection Money Heist existante ;
- `ZIGZAG` : dernier pivot confirmé du kind demandé, avec `max_bars_since` éventuel, ou pivot dans une fenêtre précédente.

Les IDs indicateurs et events sont validés contre les registries 24A.2/24A.3. Les types/status patterns et kinds ZigZag sont des enums canoniques.

### Temps et lookback

`AT_ANCHOR` :

- états (indicator/structure/current pattern status) = dernière observation disponible `<= anchor_at` ;
- événements ponctuels = distance de barre 0.

`WITHIN_PREVIOUS_BARS(N)` signifie strictement les distances 1..N. La barre anchor n'est donc pas incluse ; la borne `T-N` est incluse.

Les distances sont calculées sur les timestamps de snapshots indicateurs canoniques du timeframe : le resolver ne déduit pas une durée arbitraire en heures.

### MTF

Les conditions MTF sont supportées en v1. Pour une condition 4h à un anchor 1h, le resolver utilise la dernière observation 4h déjà disponible à l'instant de l'anchor. La projection `MarketStructureContextV1` réutilisée par Analytics est elle-même construite sur des bougies closes uniquement ; aucune bougie 4h en formation n'est introduite par 24A.7.

## Sequence DSL v1

Une `AnalyticsSequenceDefinition` contient entre 2 et 10 `AnalyticsSequenceStep`.

- la première étape ne définit pas `within_bars` ;
- chaque étape suivante exige `within_bars >= 1` ;
- `A THEN B within 5 bars` signifie `1 <= bar_distance(A,B) <= 5` ;
- `THEN` est strict : même barre rejetée, car l'OHLCV ne fournit pas d'ordre intrabar ;
- seules les séquences complètes sont publiées ; les partials ne sont pas persistées ;
- le match n'existe qu'au timestamp de la dernière étape ; aucune back-propagation n'est possible ;
- les `final_conditions` sont évaluées au timestamp de complétion.

### Matching multiple

Politique v1 : pour chaque occurrence finale, le resolver remonte la séquence et choisit à chaque étape le **prédécesseur compatible le plus récent**. Cela correspond à une politique déterministe/bornee et évite l'explosion combinatoire de tous les chemins possibles. Des occurrences finales distinctes peuvent produire des matches distincts.

## Identités et révisions

Les définitions sont `dataclass(frozen=True)` et possèdent :

- `definition_id` : identité logique stable ;
- `revision_number` ;
- `revision_id` déterministe ;
- `definition_fingerprint` déterministe ;
- `origin_period_role` (`DESIGN`, `VALIDATION`, `OOS`) ;
- versions de schéma/résolveur.

Un changement matériel (seuil, opérateur, anchor, lookback, timeframe, resolver version) doit produire une nouvelle révision/fingerprint. La même révision doit être conservée lorsqu'une hypothèse figée passe de DESIGN vers VALIDATION/OOS.

## Explainability

Chaque `AnalyticsContextMatch` conserve les `ConditionEvaluation` ayant justifié le match : valeur observée, opérateur, valeur attendue, source, instant de disponibilité et evidence. Les `AnalyticsSequenceMatch` conservent le chemin complet des steps, les sources et les final conditions.

Les évaluations qui échouent ne sont pas persistées en tant que matches v1, afin d'éviter une explosion volumétrique. L'évaluation interne reste explicite pour les tests et diagnostics.

## No-lookahead

Les invariants principaux sont :

```text
Contexts(full_dataset, as_of=T) == Contexts(prefix_at_T, as_of=T)
Sequences(full_dataset, as_of=T) == Sequences(prefix_at_T, as_of=T)
```

Ajouter des indicateurs/events/pivots/transitions futurs ne peut pas modifier une résolution à T.

## Frontière 24B

24A.7 produit des identités propres (`analytics_run_id`, research run, definition revision, `as_of`, source refs/fingerprints) qui permettront à 24B de joindre ces artefacts à `CandidateOpportunity`/Scanner au même `observed_at`. Ce join n'est pas implémenté ici.

## Discipline de recherche

Un Context/Sequence est une **hypothèse descriptive**, pas une preuve de valeur prédictive. 24A.7 n'intègre ni ranking, ni auto-discovery, ni tuning automatique, ni Forward Outcomes, ni P&L/MFE/MAE.

## Component manifest integration

Batch 24A.7 exposes `causal_research_component_versions()` with bundle version
`analytics-lab-24a7-contexts-sequences-v1`. The manifest carries the installed
context and sequence resolver versions instead of `not-installed`.
