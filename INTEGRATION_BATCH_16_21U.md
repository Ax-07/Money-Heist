# Batch 16.21u — Finalize Grounding + MTF Time Semantics

## Contexte

Le rerun LIVE_EVAL d'un mois sur
`e8ff3a6d3509572ee0bf6a2f5e8c5aa4a27f8be1` a confirmé que le Batch 16.21t
corrigeait massivement le grounding des spécialistes : la chaîne a produit des
revues Palermo, des finalisations, des propositions, des ordres, des trades et
un catalogue Denver réel.

Deux défauts résiduels ont toutefois été observés :

1. le Professor FINALIZE fabriquait encore des namespaces inexistants comme
   `market_context.specialist_analyses[0].stance` ou
   `market_context.palermo_review.verdict`, alors que ces objets sont des champs
   de premier niveau du payload FINALIZE ;
2. Palermo, et parfois le Professor, interprétaient la différence entre les
   `close` 15m/1h/4h/1d au même `observed_at` comme une incohérence temporelle.

## Sémantique MTF correcte

`observed_at` est le **decision as-of** commun du contexte.

Chaque timeframe est construit uniquement à partir des bougies complètement
clôturées disponibles à cet instant. Le dernier chandelier 15m, 1h, 4h ou 1d
peut donc avoir un endpoint différent et, naturellement, un `close` différent.

Une différence de `close` entre timeframes n'est donc pas, à elle seule, une
corruption, une désynchronisation ou une contradiction.

## Correctif

- Le prompt Professor `v3` est conservé ; la production passe à `v4`.
- Le prompt Palermo `v2` est conservé ; la production passe à `v3`.
- FINALIZE reçoit désormais `allowed_evidence_source_keys`, calculé
  déterministement depuis les entrées réelles :
  - `opportunity`
  - `market_context`
  - `specialist_analyses`
  - `palermo_review`
  - `task_force_report` lorsqu'il est fourni.
- La liste est calculée avant son injection et ne peut donc pas se citer elle-même.
- Professor `v4` doit copier les `evidence.source_key` verbatim depuis cette liste.
- `specialist_analyses` et `palermo_review` sont explicitement déclarés comme
  namespaces de premier niveau.
- Professor `v4` et Palermo `v3` documentent la sémantique MTF des derniers
  chandeliers complètement clôturés.
- Le validateur final fail-closed du pipeline n'est pas assoupli.

## Non-changements

Aucun changement sur :

- Scanner et cadence de décision 1h ;
- Feature Engine ;
- construction/resampling MTF ;
- Compute Gate ;
- spécialistes et leurs prompts v2 ;
- Rio historique ;
- Denver ;
- Risk Engine ;
- PaperBroker ;
- règles de trading ;
- paramètres de risque.

## Régressions

Les tests vérifient notamment :

1. Professor et Palermo utilisent les nouvelles versions sans supprimer les anciennes ;
2. FINALIZE expose les vrais chemins
   `specialist_analyses.0...` et `palermo_review...` ;
3. les anciennes formes invalides sous `market_context` ne sont pas autorisées ;
4. les notations `$` et `[0]` ne sont pas exposées par le contrat ;
5. le catalogue de chemins ne se cite pas lui-même ;
6. les prompts core définissent explicitement `observed_at` comme decision as-of
   et autorisent des closes MTF différents.

## Validation attendue

Après tests locaux et commit, refaire une dernière campagne **1 mois LIVE_EVAL**
avec la même configuration scientifique que le rerun précédent.

Ne pas passer au 3 mois avant d'avoir vérifié :

- chute nette des échecs FINALIZE de grounding ;
- disparition des fausses objections Palermo sur la différence de closes MTF ;
- maintien du comportement fail-closed ;
- passage normal `PLAN -> spécialistes -> Palermo -> FINALIZE`.
