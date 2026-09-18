# Money Heist — Batch 24D.2 — Scanner Filtering Quality Research

**Statut :** implémentation 24D.2  
**Policy :** `scanner-filtering-quality-descriptive-v1`  
**Source canonique :** `DecisionQualityResearchBundle.scanner_records`  
**Baseline d'entrée :** `3bbba90e60956720e8dc0ba6c378bd17196f3b76`

## 1. Objet

24D.2 mesure de façon descriptive si les cohortes produites par le Scanner sont suivies de
profils de mouvement différents. Le rapport ne juge pas le Scanner et ne simule aucune
stratégie alternative.

Le builder public est :

```python
build_scanner_filtering_quality_report(bundle=research_bundle)
```

Il est pur, déterministe, sans I/O, sans accès base de données, réseau, OpenAI, exchange,
Scanner, Feature Engine, agents, Risk, PAPER/LIVE ou moteur de Forward Outcomes.

## 2. Scanner sans direction

Le Scanner Money Heist score des événements et peut créer une `CandidateOpportunity`, mais il
ne choisit ni `LONG` ni `SHORT`. En conséquence, un mouvement futur haussier après un
`NO_TRIGGER` n'est pas automatiquement un LONG manqué et un mouvement baissier n'est pas
automatiquement une bonne décision de filtrage.

La règle méthodologique est :

```text
future price outcome != hypothetical trade P&L
```

Pour les observations filtrées, le Scanner ne définit ni direction, ni entrée, ni stop, ni
target, ni sizing. `CandidateOpportunity` n'est pas non plus synonyme de trade : Compute Gate,
Professor, spécialistes, Palermo et Risk interviennent après le Scanner.

## 3. Séparation causale / post-hoc

24D.2 ne refait aucun join 24D.1 et ne relit jamais les candles. Il consomme :

- `ScannerResearchRecord.causal` pour les faits connus à T ;
- `ScannerResearchRecord.posthoc.future_outcome` pour les métriques futures canoniques 23A ;
- uniquement les horizons `H1`, `H3`, `H5`, `H10`, `H20`.

Les records sans Forward Outcome restent dans les counts Scanner et dans la couverture. Ils ne
contribuent à aucune statistique de prix.

## 4. Classifications primaires

Les trois cohortes principales sont conservées telles quelles :

```text
NO_TRIGGER
TRIGGER_BELOW_CANDIDATE_THRESHOLD
CANDIDATE_OPPORTUNITY
```

Le rapport expose les counts et les rates de sélection correspondants, ainsi que :

```text
triggered_count = below_threshold_count + candidate_count
```

Ces métriques décrivent la sélectivité observée ; elles ne constituent pas un score de qualité.

## 5. Dimensions v1

Les dimensions versionnées de 24D.2 sont :

| Dimension | Cardinalité | Sémantique |
|---|---:|---|
| `CLASSIFICATION` | exclusive | les trois classifications canoniques |
| `SCORE` | simple | score exact observé, sans créer 101 groupes vides |
| `SCORE_MARGIN` | simple | `score - candidate_threshold`, valeur exacte |
| `TRIGGER` | **multi-valuée** | un scan peut contribuer à plusieurs cohorts |
| `MARKET_REGIME` | simple, nullable | régime causal lorsqu'il existe |

`TRIGGER_SET` n'est pas inclus dans la v1 afin d'éviter une explosion combinatoire sans besoin
démontré.

### SCORE et SCORE_MARGIN

La clé sérialisée reste stable (`key`) et les dimensions numériques portent aussi
`numeric_value: int`. Le tri est donc numérique et non lexical : `-10, -2, -1, 0, 1`, jamais
`-1, -10, -2`.

L'analyse par `SCORE_MARGIN` exact permet d'inspecter `-2`, `-1`, `0`, `+1`, etc. sans simuler
un autre threshold.

### MARKET_REGIME manquant

`market_regime=None` reste manquant. 24D.2 ne le transforme pas silencieusement en `UNKNOWN`.
Le record est compté dans `dimension_coverage.missing_scanner_count` et n'est placé dans aucune
cohorte de régime.

### TRIGGER multi-valué

`TRIGGER` porte `multi_valued=true`. La somme des counts des cohorts trigger peut donc dépasser
le nombre de scans déclenchés et ne doit jamais être utilisée comme conservation globale.

## 6. Statistiques par horizon

Chaque cohorte expose, pour H1/H3/H5/H10/H20 :

- `scanner_count` ;
- `outcome_available_count` et `outcome_missing_count` ;
- `complete_count` et `incomplete_count` ;
- counts d'incomplétude `GAP`, `PERIOD_END`, `GAP_AND_PERIOD_END` ;
- moyenne et médiane de `return_pct` ;
- counts positif/négatif/flat ;
- moyenne et médiane de `max_upside_pct` ;
- moyenne et médiane de `max_downside_pct` avec signe canonique préservé ;
- moyenne et médiane de `max_absolute_excursion_pct` ;
- counts first-hit upside/downside/same-candle ;
- rates déterministes utiles aux contrasts.

Les raw counts restent toujours disponibles. Toute rate dont le dénominateur vaut zéro est
`None`, jamais un faux zéro observé.

## 7. Max absolute excursion

Pour un horizon complet uniquement :

```text
max_absolute_excursion_pct = max(
    max_upside_pct,
    abs(max_downside_pct),
)
```

Cette métrique mesure l'amplitude maximale observée depuis le close de référence sans choisir de
direction. Elle ne représente pas un P&L réalisable.

`return_pct` signé est conservé comme statistique secondaire. Un mouvement de `+5 %` et un
mouvement de `-5 %` peuvent tous deux signaler une forte excursion pour un Scanner qui ne prend
pas lui-même de direction.

## 8. Outcomes incomplets

Un horizon `GAP`, `PERIOD_END` ou `GAP_AND_PERIOD_END` :

- est compté dans `incomplete_count` et dans son reason count ;
- est exclu de toutes les moyennes, médianes, excursions et rates first-hit ;
- n'est jamais imputé à zéro ;
- n'est jamais approximé à partir des bars disponibles.

La conservation par cohorte/horizon est :

```text
outcome_available_count + outcome_missing_count = scanner_count
complete_count + incomplete_count = outcome_available_count
positive + negative + flat = complete_count
upside first-hit + downside first-hit + same-candle = complete_count
```

## 9. Contrasts v1

Trois contrasts descriptifs sont produits :

```text
CANDIDATE vs BELOW_THRESHOLD
CANDIDATE vs NO_TRIGGER
BELOW_THRESHOLD vs NO_TRIGGER
```

Pour chaque horizon, ils exposent les différences gauche moins droite de :

- médiane `return_pct` ;
- médiane `max_upside_pct` ;
- médiane `max_downside_pct` ;
- médiane `max_absolute_excursion_pct` ;
- part positive ;
- part first-hit upside ;
- part first-hit downside.

Aucun champ `winner`, ranking, `GOOD/BAD`, quality score ou recommandation n'est créé.

## 10. Couverture avant interprétation

Le rapport expose explicitement :

```text
scanner_records
with_future_outcome / without_future_outcome
with_analytics / without_analytics
per-horizon complete / incomplete
```

Un record `MISSING_ANALYTICS` qui possède un Forward Outcome valide continue de contribuer aux
statistiques Scanner/outcome. L'absence Analytics reste une information de couverture et ne
supprime pas le record.

Les petits groupes, y compris `N=1`, sont conservés. 24D.2 n'émet ni p-value, ni niveau de
confiance, ni affirmation de significativité statistique.

## 11. Discipline DESIGN / VALIDATION / OOS

Un rapport hérite d'un seul `period_role` de son `DecisionQualityResearchBundle` : `DESIGN`,
`VALIDATION` ou `OOS`. 24D.2 n'agrège jamais ces rôles automatiquement.

Les résultats DESIGN peuvent nourrir une hypothèse future. Ils ne changent pas automatiquement
le Scanner avant VALIDATION/OOS. Un OOS observé ne doit pas être réutilisé pour retuner puis
présenté comme le même OOS intact.

## 12. Déterminisme et versionnage

Contrats :

```text
money-heist.scanner-filtering-quality-report.v1
money-heist.scanner-filtering-cohort.v1
money-heist.scanner-filtering-contrast.v1
```

Le `report_id` est déterministe à partir de l'identité matérielle du rapport. Le
`report_fingerprint` inclut notamment :

- la policy 24D.2 ;
- le `source_bundle_fingerprint` 24D.1 ;
- les summaries/couvertures ;
- les cohort fingerprints ;
- les contrasts.

Chaque cohort fingerprint est déterministe à partir de la policy, de l'identité du research run,
de la dimension/clé, des fingerprints des Scanner records membres et des statistiques produites.
Aucun wall-clock timestamp n'entre dans ces identités.

La sérialisation `to_json()` réutilise `canonical_json`; les IDs/fingerprints réutilisent
`stable_uuid` et `stable_digest`.

## 13. Ce que le rapport permet de dire

Exemples valides :

- « La médiane de l'excursion absolue H10 diffère entre Candidate et BelowThreshold. »
- « Les scans `score_margin=-1` présentent ce profil descriptif post-hoc. »
- « Le trigger X apparaît dans N scans et possède cette distribution post-hoc. »
- « La couverture outcome H20 est plus faible que H10 sur cette période. »

Ces formulations décrivent des associations observées et non des effets causaux.

## 14. Ce que le rapport ne permet pas de dire

24D.2 ne permet pas d'affirmer :

```text
Threshold 35 est optimal.
Un NO_TRIGGER était un trade raté.
Le Scanner aurait dû prendre ce trade.
Le threshold devrait être abaissé à 30.
Baisser le threshold créerait X trades.
Cette cohorte est la gagnante.
```

Aucune simulation de threshold alternatif, aucun `MISSED_OPPORTUNITY`, aucun trade
contrefactuel, aucun tuning Scanner, agent/risk/prompt et aucun machine learning ne font partie de
24D.2.

## 15. Persistance et UI

24D.2 produit uniquement un rapport canonique sérialisable en mémoire. Il n'ajoute :

- aucune persistance automatique ;
- aucun endpoint GET qui calcule à la demande ;
- aucun composant frontend ;
- aucun branchement dans `analytics_postrun.py`.

La projection/persistance/navigation de rapports est réservée à 24D.4 — Research Reports &
Evidence Explorer.

## 16. Suite

La suite fonctionnelle reste :

```text
24D.1 — Research Foundation & Outcome Join         DONE
24D.2 — Scanner Filtering Quality Research         CURRENT
24D.3 — Funnel Decision Quality Research           NEXT
24D.4 — Research Reports & Evidence Explorer       PLANNED
```

24D.3 pourra appliquer la même discipline au Compute Gate, Professor, spécialistes, Palermo,
FINAL et Risk face aux outcomes futurs, sans modifier le périmètre 24D.2.
