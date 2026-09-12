# Batch 16.21t — LIVE_EVAL Evidence Path Grounding

## Contexte

Le premier backtest LIVE_EVAL d'un mois sur le commit
`b96393d0fa3281dd7f27f7844b177687939a9c51` a confirmé le fonctionnement du
provider OpenAI, du budget dur, de Rio historique et des contrôles fail-closed,
mais a aussi montré qu'un grand nombre de réponses Berlin/Tokyo/Nairobi
fabriquaient des variantes syntaxiques ou sémantiques de `source_key`.

Exemples observés :

- `market_context.market.snapshots.1h.rsi_14`
- `market_context.structure.payload.timeframes.1h.breakout_state`
- `$.market_context.decision_context.market.snapshots["1h"].ema_spread_pct`

Le contexte MTF réellement fourni utilise notamment :

- `market_context.decision_context.market.snapshots.<tf>.<field>`
- `market_context.decision_context.structure.payload.timeframes.<tf>.<field>`

Les contrôles de grounding les rejetaient correctement, mais après consommation
de tokens API.

## Correctif

- Les prompts spécialistes `v1` restent inchangés et adressables.
- Berlin, Tokyo, Nairobi, Rio et Denver passent au prompt `v2`.
- Chaque requête spécialiste `v2` reçoit
  `allowed_evidence_source_keys`, liste triée et déterministe calculée uniquement
  à partir des chemins réellement présents sous `opportunity`, `market_context`
  et, lorsqu'il existe, `specialist_context`.
- Le prompt `v2` exige que chaque `evidence.source_key` soit copié verbatim depuis
  cette liste.
- Les alias, préfixes `$`, notation par crochets et segments omis/ajoutés sont
  explicitement interdits.
- Le validateur fail-closed `_assert_grounded_evidence` n'est pas assoupli.
  Une clé absente des entrées réelles reste rejetée.

## Non-changements

Aucun changement sur :

- Scanner ou cadence 1h ;
- Feature Engine / MTF ;
- Risk Engine ;
- PaperBroker / exécution ;
- logique de sélection du Compute Gate ;
- Palermo ;
- Professor FINALIZE ;
- Rio archive / Denver attribution ;
- règles trading ou paramètres de risque.

## Régressions

Les tests couvrent désormais :

1. présence déterministe de `allowed_evidence_source_keys` en prompt spécialiste v2 ;
2. chemin MTF exact accepté ;
3. variante sémantique raccourcie toujours rejetée fail-closed ;
4. prompts v1 toujours disponibles ;
5. registre de production utilisant les prompts spécialistes v2.

## Validation LIVE_EVAL attendue

Après tests locaux et commit, refaire le **même backtest 1 mois** :

- dataset annuel BTC/USDC 15m ;
- Rio historique ON, fraîcheur 7200 s ;
- Denver OFF ;
- IA `LIVE_EVAL` ;
- Walk-forward OFF ;
- nouveau SHA de commit comme `code_version` ;
- budget dur recommandé pour ce rerun : `1.00 EUR`.

Ne pas passer à 3 mois tant que le rerun 1 mois n'a pas montré une chaîne
`PLAN -> spécialistes -> Palermo -> FINALIZE` normalement traversée et un taux
d'échec de grounding redevenu marginal.
