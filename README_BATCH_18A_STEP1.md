# Batch 18a — Step 1 — Réputation & ablation déterministes

## Périmètre

Ce sous-lot ajoute une couche d'évaluation uniquement.

- comparaison d'ablation stricte baseline vs run sans exactement un agent ;
- comparabilité : même fingerprint expérimental, dataset, rôle, période,
  nombre de bougies et opportunités ;
- deltas trading/economic net, drawdown et coût IA ;
- agrégation OOS explicite ;
- profil de réputation multidimensionnel sans score global opaque ;
- suggestion d'état SHADOW / PROBATION / ON_DEMAND ;
- aucune mutation automatique du registry ;
- aucune capacité LIVE, broker, exchange ou Risk Engine.

## Convention de signe

- `marginal_trading_net = baseline - ablated` : positif => contribution observée positive ;
- `marginal_economic_net = baseline - ablated` : positif => contribution nette après coût IA ;
- `drawdown_reduction_pct = ablated - baseline` : positif => drawdown réduit avec l'agent ;
- `additional_ai_cost_eur = baseline - ablated` : coût IA additionnel observé.

## Important

Une ablation est une comparaison expérimentale, pas une preuve causale universelle.
Les runs non comparables sont rejetés et les métriques indisponibles ne sont jamais inventées.
