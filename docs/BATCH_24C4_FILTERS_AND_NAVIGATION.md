# Money Heist — Batch 24C.4 — Filters & Navigation

**Date :** 2026-09-18
**Baseline auditée :** `f32b41f4c1f432b46212721d996d657cffa97c2f`
**Statut :** implémentation frontend prête à intégrer
**Périmètre :** exploration read-only des projections 24C ; aucune modification du pipeline métier.

## 1. Décisions d'architecture

Le Batch 24C.4 étend l'état Zustand déjà introduit en 24C.2 au lieu de créer un second store. La séparation reste :

```text
Backend canonical artifacts
        ↓
24C projections read-only
        ↓
frontend filtering / navigation
```

Aucun filtre ne modifie Scanner, CandidateOpportunity, agents, Professor, Palermo, Risk, PAPER, Forward Outcomes, `BacktestRun.run_id` ou le business fingerprint.

Le backend 24C.1/24C.2 contient déjà toutes les données nécessaires. **Aucune extension backend/API/Zod n'est requise dans 24C.4.**

## 2. Filtres V1 retenus

### Scanner

- `classification` : multi-select ;
- `triggers` : multi-select ;
- `score` : bornes min/max inclusives sur la valeur projetée `score`.

Les valeurs réellement présentes dans le run alimentent les options dynamiques.

### Decision Funnel

- Professor FINAL : multi-select (`LONG`, `SHORT`, `NO_TRADE` lorsque présents) ;
- Palermo : multi-select (`CLEAR`, `CAUTION`, `REJECT` lorsque présents) ;
- Risk : multi-select (`APPROVED`, `RESIZED`, `REJECTED` ou valeurs réellement projetées).

### Analytics

- Technical Event : `family`, `event_type`, `direction` en multi-select ;
- Pattern : `pattern_type`, statut causal, `direction`, `pivot_source` en multi-select.

Les filtres Structure et ZigZag ne sont pas ajoutés en V1 : ces objets restent navigables, mais le batch évite volontairement un langage de requête universel.

## 3. Sémantique AND / OR

Règle unique :

```text
OR à l'intérieur d'une dimension
AND entre dimensions
```

Exemple :

```text
Risk = REJECTED OR RESIZED
AND
Palermo = CAUTION
```

Lorsqu'une dimension décisionnelle aval est active, elle devient l'ancre du résultat : `Risk` puis `FINAL` puis Palermo. Cette règle évite qu'un résultat futur rende rétroactivement un Candidate compatible avant que la décision aval soit connue.

## 4. Visibility ≠ Filter ≠ Search

`overlayVisibility` reste indépendant de `overlayFilters`.

- Visibility OFF : la couche n'est pas dessinée ;
- Filter : l'objet doit correspondre pour entrer dans les résultats/overlays filtrés ;
- Search : recherche locale temporaire dans la liste filtrée par ID, label, type et détails ; elle n'est ni persistée ni convertie en filtre global.

`Réinitialiser les filtres` restaure uniquement `overlayFilters` et ne modifie pas la visibilité.

## 5. Modèle central

La logique pure vit dans :

```text
frontend/src/lib/decision-intelligence-navigation.ts
```

Elle centralise :

- construction des `FilteredNavigationItem` ;
- disponibilité causale ;
- facettes ;
- AND/OR ;
- tri déterministe ;
- recherche ;
- Previous/Next ;
- position courante ;
- labels des filtres actifs.

Le chart, le compteur, la liste et Previous/Next utilisent ce même résultat. Les composants React ne réimplémentent pas des `.filter()` métier concurrents.

## 6. Timestamp de géométrie vs timestamp de navigation

`OverlaySelection` conserve maintenant deux temps distincts :

```text
timestamp            = ancrage géométrique sur le chart
navigationTimestamp  = instant causal auquel l'objet est disponible
```

Politique :

| Objet | Géométrie | Navigation causale |
|---|---|---|
| Scanner / Candidate | `observed_at` | `observed_at` |
| Technical Event | `event_at` | `available_at` |
| ZigZag pivot | `pivot_at` | `confirmed_at` |
| Pattern | pivot géométrique / détection | `available_at` de la dernière transition causale visible |
| Funnel / Palermo / FINAL / Risk | `market_as_of` | `operational_at ?? market_as_of` |
| Structure | `as_of` | `as_of` |

Cette séparation permet par exemple de dessiner un pivot à 08:00 tout en naviguant à 14:00 si sa confirmation n'existe qu'à 14:00.

## 7. Causalité du filtering

Les objets sont d'abord bornés par le scope causal courant. Les facettes Decision sont reconstruites uniquement à partir des stages déjà opérationnels à l'instant concerné. Une décision Risk future ne peut donc pas faire matcher rétroactivement un Candidate plus ancien.

Les patterns utilisent leur historique de transitions `available_at`; `current_status` final n'est jamais back-propagé au curseur.

## 8. Navigation Previous / Next

Ordre déterministe :

```text
timestamp causal
→ ordre canonique de type
→ ID stable
```

La navigation ne wrappe pas :

- premier résultat → Previous désactivé ;
- dernier résultat → Next désactivé.

Lorsqu'une navigation filtrée commence, le cockpit conserve le **scope causal de départ** pendant le parcours. Le replay peut donc se déplacer en arrière sans que la liste disparaisse à chaque saut. Un déplacement manuel du replay réinitialise ce scope à la nouvelle position.

À chaque navigation :

1. l'objet devient la sélection Zustand ;
2. `selectedOpportunityId` est synchronisé si disponible ;
3. `seekTo()` place le replay sur `navigationTimestamp` ;
4. la lecture passe à `playing = false` ;
5. l'Inspector 24C.3 est conservé comme panneau de détail unique.

## 9. Sélection hors filtre

Un changement de filtres ne ferme pas l'Inspector et ne remplace pas automatiquement la sélection. Si la sélection courante ne correspond plus, la toolbar affiche `sélection hors filtre`.

Previous/Next et la liste utilisent uniquement les résultats filtrés.

## 10. Campaign / role changes

Un changement de :

```text
campaign_id
DESIGN / VALIDATION / OOS
```

réinitialise :

- sélection Analytics ;
- opportunité sélectionnée ;
- position/scope de navigation ;
- lecture du replay.

Les préférences génériques de filtres et de visibilité restent persistées.

## 11. Zustand persistence et migration

Store conservé :

```text
money-heist-ui-v2
```

Version persistée : `2`.

Persisté :

- `sidebarCollapsed` ;
- `overlayVisibility` ;
- `overlayFilters`.

Non persisté :

- `selectedOpportunityId` ;
- `selectedAnalyticsObject` ;
- résultat/navigation courante ;
- recherche texte.

La migration accepte l'ancien état 24C.2 :

```text
technicalEventFamily: string | null
technicalEventType: string | null
```

et le normalise vers les nouveaux multi-selects sans crash.

## 12. UX

La petite `OverlayToolbar` reste dédiée aux toggles rapides, au bouton Filters, au compteur et à Previous/Next. Les contrôles détaillés vivent dans un Dialog responsive organisé en :

```text
Scanner
Decision Funnel
Analytics
```

Le panneau contient également la liste de résultats et une recherche ID/label/type. Les candles ne sont jamais filtrées.

## 13. Deep linking

Aucun deep-link URL n'est ajouté dans ce lot. Le routing App Router actuel ne porte pas encore ce state ; ajouter `?role=...&opportunity=...` aurait étendu le scope sans nécessité pour les objectifs V1.

## 14. Backend / contrats

Aucun fichier backend métier n'est modifié. Aucun nouvel endpoint n'est créé. Les projections existantes suffisent : Scanner, Funnel, Technical Events, Structure, ZigZag et Patterns.

Les sidecars :

```text
frontend-decision-intelligence-*.json
frontend-analytics-overlays-*.json
```

restent canoniques et indépendants des préférences UI.

## 15. Tests ajoutés / renforcés

La suite frontend couvre notamment :

- Scanner `NO_TRIGGER`, `TRIGGER_BELOW_CANDIDATE_THRESHOLD`, `CANDIDATE_OPPORTUNITY` ;
- triggers OR ;
- bornes score inclusives ;
- FINAL ;
- Palermo ;
- Risk ;
- AND/OR explicite ;
- Technical Events family/type/direction ;
- Pattern type/status/direction/pivot source via le moteur central ;
- absence de look-ahead Risk ;
- pivot `pivot_at != confirmed_at` ;
- event `event_at != available_at` ;
- pattern transition causale ;
- funnel `market_as_of != operational_at` ;
- tri stable ;
- Previous/Next sans wrap ;
- ancienne persistence Zustand 24C.2 ;
- sélection run-specific non restaurée.

## 16. État Batch 24C

```text
24C.1 — Backend Projection API              DONE
24C.2 — Trading Chart Analytics Overlays    DONE
24C.3 — Decision Intelligence Inspector     DONE
24C.4 — Filters & Navigation                DONE

Batch 24C — Decision Intelligence Backend & UI
DONE
```

La phase suivante reste :

> **Batch 24D — Decision Quality Research**

24C.4 ne joint aucun Forward Outcome, ne classe aucune opportunité et n'effectue aucun tuning.
