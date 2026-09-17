# Money Heist — Batch 24C.2 — Trading Chart Analytics Overlays

**Baseline auditée :** `1abe9becaac554a08f2eb87336bcda2b34c8735e`
**Dernier commit baseline :** `fix(docs): restore 24C.1 UTF-8 encoding`
**Statut :** implémentation 24C.2
**Autorité :** affichage read-only, projection-only, aucune autorité de trading

## 1. Objectif

24C.2 transforme le chart Historical Replay existant en outil d'inspection causal sans créer un
second moteur de chart et sans recalculer les artefacts métier dans le navigateur.

```text
Artefacts Backtest / 24A / 24B pré-calculés
        ↓
Projection frontend read-only
        ↓
GET /api/frontend/v2/backtests/runs/{campaign_id}/analytics/overlays
        ↓
Zod + TanStack Query
        ↓
TradingChartAdapter / Lightweight Charts
```

Le Scanner, les agents, Palermo, le Risk Engine, PAPER, LIVE et les Forward Outcomes ne sont pas
modifiés par ce batch.

## 2. Audit de la baseline

La baseline 24C.1 fournit déjà :

- `GET .../analytics` pour l'identité Analytics et une timeline légère ;
- `GET .../analytics/scanner` pour toutes les évaluations Scanner ;
- `GET .../opportunities/{id}/decision-intelligence` pour le funnel décisionnel ;
- les schémas Zod et hooks préparatoires ;
- un Historical Replay V2 avec curseur causal ;
- un unique `TradingChartAdapter` basé sur Lightweight Charts ;
- candles, volume et markers replay existants ;
- Zustand pour l'état UI global.

24C.1 ne projetait volontairement pas la géométrie riche 24A. Les objets canoniques restent dans
`AnalyticsSnapshot.components` : `technical_events`, `market_structure`, `zigzag_pivots` et
`patterns`.

## 3. Endpoint overlays

24C.2 ajoute de manière additive :

```text
GET /api/frontend/v2/backtests/runs/{campaign_id}/analytics/overlays?role=OOS
```

Le payload combine :

- Scanner 24B.3 ;
- funnel stages 24B.4 ;
- Technical Events 24A.3 ;
- Market Structure 24A.4 ;
- Causal ZigZag 24A.4 ;
- Patterns 24A.5.

Les géométries 24A sont projetées depuis les objets déjà calculés. Le service ne lit pas les
candles et ne possède aucune fonction de calcul d'indicateur, de Scanner, de Risk ou de pattern.

### Persistance

La géométrie riche est persistée sous :

```text
frontend-analytics-overlays-design.json
frontend-analytics-overlays-validation.json
frontend-analytics-overlays-oos.json
```

Le helper `build_frontend_analytics_geometry_projection()` reçoit les `AnalyticsSnapshot`
canoniques déjà construits. `persist_frontend_analytics_geometry_projection()` persiste ensuite
la projection dans le sidecar frontend existant.

Cette étape doit être appelée au même endroit que la production/persistance pré-calculée de 24C.1.
Elle ne relance aucun moteur Analytics. Un bundle 24C.1 sans géométrie 24C.2 reste utilisable :
Scanner et funnel sont disponibles, les familles géométriques sont simplement vides.

## 4. Overlay architecture

Le composant React principal ne manipule pas directement toute la logique Lightweight Charts.

```text
BacktestDetail
  ├─ OverlayToolbar
  └─ TradingChart
       └─ TradingChartAdapter
            ├─ candles + volume existants
            ├─ markers replay Trading
            ├─ markers Analytics / Decision
            ├─ série Line ZigZag
            └─ séries Line PatternSegment
```

`analytics-overlays.ts` est la couche de mapping pure : DTO backend → modèle chart. Elle centralise
la conversion ISO UTC → `Time`, le filtrage causal et la sélection stable.

## 5. Causalité du replay

Le curseur du replay est l'autorité de visibilité.

### Technical Events

```text
position graphique = event_at
visible à partir de = available_at
```

Un événement dont `available_at` est futur par rapport au curseur n'est pas rendu.

### ZigZag causal

```text
position graphique = pivot_at
connu à partir de = confirmed_at
```

Le pivot n'est jamais révélé avant `confirmed_at`. Une fois connu, sa ligne et son marker sont
placés à la position historique `pivot_at`. Le détail cliquable affiche explicitement les deux
timestamps, l'ATR au pivot, le seuil de retournement et les amplitudes disponibles.

### Patterns

La géométrie vient exclusivement des `PatternPoint` et `PatternSegment` backend.
Le statut affiché au curseur est dérivé de la dernière `PatternTransition.available_at <= T`.

Exemple :

```text
CONFIRMED disponible à T8
FAILED disponible à T12
curseur T10 → CONFIRMED
```

`current_status=FAILED` dans l'objet final n'est donc jamais rétro-propagé avant T12.

### Funnel décisionnel

Les stages FINAL / Palermo / Risk conservent `market_as_of` comme position de marché. Pour la
visibilité causale, `operational_at` est utilisé lorsqu'il existe ; sinon le système retombe sur
`market_as_of`. Les deux timestamps restent donc distincts et une décision opérationnellement
future n'est pas révélée au curseur.

## 6. Overlays et visibilité par défaut

| Famille | Défaut | Raison |
|---|---:|---|
| Trading replay | ON | conserver entrées/sorties/ordres/fills existants |
| CandidateOpportunity | ON | événement décisionnel principal |
| Scanner below threshold | OFF | réduire la densité |
| Scanner NO_TRIGGER | OFF | éviter des milliers de markers |
| Professor FINAL LONG/SHORT | ON | décision finale utile |
| FINAL NO_TRADE | OFF | forte densité possible |
| Palermo | OFF | couche d'inspection indépendante |
| Risk | ON | autorité déterministe importante |
| Technical Events | OFF | densité potentiellement forte |
| Structure | OFF | réduire les labels simultanés |
| ZigZag | ON | structure causale lisible |
| Patterns | ON | patterns disponibles et connus |
| Patterns FORMING | OFF | conserver le chart lisible |

Les préférences sont stockées dans Zustand et persistées avec les autres préférences UI.

## 7. Scanner density policy

Aucune observation backend n'est supprimée.

- `NO_TRIGGER` : conservé dans le DTO, caché par défaut ;
- `TRIGGER_BELOW_CANDIDATE_THRESHOLD` : marker subtil, caché par défaut ;
- `CANDIDATE_OPPORTUNITY` : marker proéminent, visible par défaut.

Le tooltip/sélection Scanner conserve classification, score, seuil candidat, marge, triggers et
market regime.

## 8. Technical Event filters

Lorsque la couche Events est activée, la toolbar expose deux filtres locaux :

```text
family
→ event_type
```

Une valeur vide signifie « tous ». Le filtre ne modifie ni ne tronque le payload backend.

## 9. Structure

24C.2 n'invente pas de labels HH/HL/LH/LL à partir des prix. La projection transporte les
`SwingPoint`, `swing_structure`, `prior_range_high/low`, `range_location` et `breakout_state`
backend. La première visualisation utilise les états breakout/retest/faux break en markers ; les
swing/range détails restent accessibles dans la sélection et pourront être enrichis en 24C.4.

## 10. ZigZag rendering

Lightweight Charts 4.2.x est conservé. Le ZigZag est une série `Line` dédiée, distincte des
candles. L'adapter crée la série une fois, met ses données à jour selon le curseur et la vide
lorsque le toggle est OFF.

Aucun pivot n'est recalculé dans React.

## 11. Pattern rendering

Chaque `PatternSegment` backend devient une série `Line` courte. Les séries sont créées/mises à
jour/supprimées par l'adapter ; elles ne modifient pas la série candle.

Le style indique le lifecycle sans signification de performance future :

- `FORMING` : dashed ;
- `CONFIRMED` : solid ;
- `FAILED` / `INVALIDATED` : dotted / neutre.

Le pattern possède aussi un marker cliquable avec type, statut au curseur, pivot source,
`detected_at`, `confirmed_at`, `failed_at`, `invalidated_at` et les pivots sources.

## 12. Sélection préparatoire à 24C.3

Un overlay cliquable produit :

```text
objectType
objectId
opportunityId
 timestamp
label
details
```

Zustand conserve :

```text
selectedOpportunityId
selectedAnalyticsObject
```

24C.2 affiche seulement un résumé compact. Le Decision Intelligence Inspector complet reste hors
scope et appartient à 24C.3.

## 13. Compatibilité anciens runs

Un run sans bundle Analytics reçoit :

```json
{
  "analytics_available": false,
  "technical_events": [],
  "structure": [],
  "zigzag_pivots": [],
  "patterns": []
}
```

Le replay classique conserve candles, events, trades et equity. La toolbar Analytics est
désactivée au lieu de faire planter la page.

Un run avec 24C.1 mais sans export de géométrie 24C.2 conserve Scanner/funnel et retourne des
listes géométriques vides.

## 14. Tests ajoutés

Backend :

- ancien run sans Analytics → dégradation explicite ;
- campagne inconnue → 404 ;
- déduplication des composants cumulés ;
- `pivot_at` distinct de `confirmed_at` ;
- rejet d'un snapshot d'un autre AnalyticsRun.

Frontend :

- validation Zod ancien run / pivot causal ;
- pivot caché avant confirmation ;
- géométrie ZigZag à `pivot_at` ;
- statut pattern non rétro-propagé ;
- `NO_TRIGGER` caché par défaut ;
- CandidateOpportunity expose `opportunity_id` ;
- toggle ZigZag OFF/ON ;
- filtres Technical Events family/type.

## 15. Isolation

24C.2 ne modifie pas :

- Scanner ;
- `CandidateOpportunity` ;
- `DecisionContext` ;
- Professor / spécialistes / Palermo ;
- Risk Engine ;
- PAPER ;
- LIVE ;
- Forward Outcomes ;
- business fingerprint ;
- `BacktestRun.run_id`.

Les imports de projection restent dans `app/services/frontend_v2` et les routes frontend.

## 16. Roadmap

```text
24C.1 — Backend Projection API              DONE
24C.2 — Trading Chart Analytics Overlays    CURRENT
24C.3 — Decision Intelligence Inspector     NEXT
24C.4 — Filters & Navigation
24D   — Decision Quality Research
```

## 17. Fichiers canoniques concernés

Les addendums de ce document doivent être reflétés dans les versions courantes de :

```text
docs/02_ARCHITECTURE.md
docs/08_API_ET_MODELES_DE_DONNEES.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/10_DECISIONS_ET_CHANGELOG.md
docs/12_FRONTEND_ET_INTERFACE.md
frontend/README.md
```

Le livrable 24C.2 ne doit jamais remplacer ces documents par une ancienne copie. Si leur contenu
`main` complet n'est pas disponible dans l'environnement de packaging, ce document de batch reste
l'addendum autoritatif à appliquer lors de l'intégration locale plutôt que d'écraser une version
plus récente.
