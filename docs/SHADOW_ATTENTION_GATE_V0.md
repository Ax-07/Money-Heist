# Money Heist — Shadow Attention Gate v0

**Statut :** CANDIDATE — validation locale requise
**Autorité :** observation-only / post-run
**But :** comparer le réveil du Scanner v1 à une attention causale issue d'Analytics sans modifier le comportement du replay.

## Principe

La Shadow Attention Gate v0 est construite uniquement après un Historical Replay terminé :

```text
Historical Replay réel
├─ Scanner v1 réel
└─ Analytics 24A / Attribution 24B
        ↓
Shadow Attention Gate v0
        ↓
rapport comparatif observationnel
```

Elle ne rappelle jamais le Scanner, n'appelle aucun agent, ne construit aucune `TradeProposal`, ne consulte pas le Risk Engine et ne déclenche aucune exécution PAPER/LIVE.

## Causes d'attention v0

Une évaluation Scanner peut recevoir `shadow_wake=true` uniquement lorsqu'au même `as_of` causal exact se produit au moins une observation parmi :

- `TECHNICAL_EVENT` disponible exactement à T ;
- confirmation `ZIGZAG` disponible exactement à T ;
- transition de pattern disponible exactement à T.

Les changements et états de structure restent **contexte-only** dans v0 et ne peuvent pas réveiller la gate à eux seuls.

Plusieurs raisons disponibles au même instant sont coalescées en une seule `ShadowAttentionObservation`. La v0 n'introduit volontairement aucun score, poids, seuil, cooldown tuné, direction LONG/SHORT ou classification de setup.

## Comparaison

Chaque évaluation Scanner existante est classée post-hoc dans une catégorie :

```text
BOTH          Scanner candidate + Shadow attention
SCANNER_ONLY  Scanner candidate sans raison v0
SHADOW_ONLY   raison v0 sans CandidateOpportunity Scanner
NEITHER       aucun des deux
UNAVAILABLE   attribution Analytics exacte absente
```

`UNAVAILABLE` est fail-closed : aucune attention n'est fabriquée lorsque la jointure Analytics exacte manque.

## Causalité

La jointure exige l'égalité stricte :

```text
ScannerObservation.observed_at
== ScannerAnalyticsRef.analytics_as_of
== AnalyticsSnapshot.as_of
```

Aucun nearest-neighbor temporel n'est autorisé. Tout objet Analytics dont `available_at` / `confirmed_at` dépasse le snapshot courant provoque une erreur.

## Expérimentation

La campagne 3 mois déjà utilisée pour explorer les biais Scanner / Analytics sert à la conception et ne constitue plus un holdout vierge pour valider un futur Attention Gate comportemental.

Après validation technique de v0, la comparaison utile doit être rejouée sur une période fraîche avant toute proposition de comportement :

```text
DESIGN exploratoire
→ hypothèse figée
→ nouvelle VALIDATION
→ nouvel OOS intact
→ PAPER / SHADOW
```

La Shadow Attention Gate v0 ne constitue ni un signal de trading ni une autorisation de remplacer Scanner v1.
