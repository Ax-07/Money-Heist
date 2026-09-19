# Money Heist — Batch 10 — Evaluation

## Base requise

Le lot est préparé pour être extrait sur le dépôt au commit :

```text
0871831 feat(paper): complete Batch 09 Paper Pipeline
```

Le dépôt doit être propre avant extraction.

## Intégration

Depuis `E:\0 money heist` :

1. extraire le ZIP directement à la racine du projet ;
2. vérifier les changements avec `git status --short` ;
3. lancer :

```powershell
uv sync
uv run pytest -q
```

Aucune migration, nouvelle dépendance ou variable d’environnement n’est nécessaire.

Les **190 tests existants** doivent rester verts. Le lot ajoute **25 tests Batch 10** ; le total attendu après intégration est donc **215 tests**.

## Architecture ajoutée

```text
Données déjà produites
├─ Paper Broker : ordres / fills / positions / frais
├─ Batch 09 : opportunity / proposal / risk decision / execution
└─ AI Gateway : usage / coût / latence / modèle / route
              ↓
      Adaptateurs Evaluation en lecture seule
              ↓
       EvaluationSource reconstruisible
              ↓
      ┌─────────────────────────────┐
      │ métriques trading           │
      │ métriques coûts IA          │
      │ métriques agents            │
      │ traçabilité                 │
      └─────────────────────────────┘
              ↓
      économie IA déterministe
              ↓
       rapport Lisbon V1
              ↓
       JSON / CSV simples
```

La couche Evaluation est **consommatrice** des données des Batchs précédents. Le pipeline PAPER, le Risk Engine et le Paper Broker n’importent pas Evaluation et ne dépendent pas de son succès pour autoriser ou reconstruire un état de trading.

## Trading Net et coûts d’exécution

Le Paper Broker actuel calcule `realized_pnl` à partir des prix de fill et conserve les frais séparément. Le slippage des ordres market est déjà incorporé dans le prix de fill.

Batch 10 expose donc explicitement :

```text
execution_realized_pnl  = PnL réalisé aux prix de fill, avant frais
fees_paid               = frais réellement enregistrés dans les fills
slippage_cost            = coût séparé si reconstructible depuis la config PAPER
gross_pnl_before_costs   = disponible uniquement si marks + slippage sont connus
realized_trading_net     = execution_realized_pnl - frais payés
trading_net              = execution_realized_pnl + unrealized_pnl - frais payés
```

Le slippage n’est jamais soustrait une seconde fois du `trading_net`, puisqu’il est déjà présent dans les prix de fill. S’il n’est pas reconstructible séparément, la métrique reste `UNAVAILABLE`.

## Métriques trading disponibles

- fills et ordres exécutés ;
- trades clôturés reconstruits selon la comptabilité moyenne du Paper Broker ;
- positions ouvertes ;
- PnL réalisé d’exécution ;
- frais ;
- slippage lorsque reconstructible ;
- PnL brut avant coûts lorsque reconstructible ;
- Trading Net réalisé ;
- PnL non réalisé lorsqu’une mark est disponible ;
- Trading Net mark-to-market lorsqu’il est calculable ;
- exposition brute ;
- win rate ;
- profit factor ;
- expectancy ;
- drawdown absolu et relatif à partir d’une série d’equity suffisante.

Les positions sont indexées par `(system_id, symbol)` afin d’éviter toute contamination future entre systèmes. Batch 10 ne crée toutefois aucun profil SHADOW.

Aucune métrique nécessitant des données absentes n’est inventée. En particulier, Batch 10 ne produit pas MAE, MFE, Sharpe, Sortino, calibration historique ou attribution marginale sans historique approprié.

## Coûts IA

Les `AIUsageRecord` du AI Gateway sont agrégés en EUR :

- total ;
- par agent ;
- par modèle ;
- par route ;
- par opportunité lorsqu’un `request_id` peut être relié à la trace Batch 09 ;
- par décision Risk Engine lorsqu’un `risk_decision_id` existe ;
- par ordre/trade PAPER exécuté lorsqu’un `broker_order_id` existe.

Les coûts qui ne peuvent pas être reliés à une opportunité restent inclus dans le total sous `unattributed_to_opportunity_eur` et ne sont pas attribués artificiellement.

Deux sources de traçabilité sont acceptées :

- le `PaperPipelineResult` riche, privilégié lorsqu'il est encore disponible ;
- les `PaperPipelineEvent` du journal Batch 09, capables de reconstruire les IDs et de rattacher les coûts via `agent_request_ids` sans inventer les détails agents absents du journal.

## Métriques agents V1

Pour Berlin, Tokyo, Nairobi, Palermo, Professor et tout autre agent réellement présent dans les données :

- nombre d’appels logiques (`request_id` uniques) ;
- nombre de tentatives AI Gateway ;
- coût total et moyen ;
- latence moyenne si disponible ;
- fréquence de participation ;
- stance observée ;
- confiance moyenne si disponible ;
- fréquence de désaccord directionnel lorsqu’elle est comparable ;
- décisions finales associées ;
- versions de prompt ;
- routes ;
- modèles.

Palermo n’ayant pas de `confidence` directionnelle dans le contrat actuel, cette métrique reste explicitement indisponible pour lui au lieu d’être inventée.

## SelfFundingRatio et Economic Net

```text
SelfFundingRatio = Trading Net disponible / coût IA
Economic Net      = Trading Net disponible - coût IA
```

Priorité de base :

1. `MARK_TO_MARKET` si le Trading Net complet est disponible ;
2. `REALIZED_ONLY` sinon.

Si le coût IA est nul, le ratio n’est pas transformé en infini :

```text
value  = None
status = ZERO_AI_COST
```

Le ratio est purement observationnel. Il n’est jamais transmis au Risk Engine et ne peut pas autoriser, redimensionner ou augmenter le risque d’un trade.

Le coût d'infrastructure attribuable n'est pas soustrait dans Batch 10 car aucune source actuelle ne le fournit. Il reste donc volontairement non inventé ; l'`Economic Net` de ce batch correspond à `Trading Net - coût IA`.

## Lisbon V1

`DeterministicLisbonReporter` construit un rapport à partir des métriques déjà calculées. Il peut produire des observations et recommandations, mais son contrat ne contient :

- aucun `RiskEngine` ;
- aucun broker ;
- aucun contrôleur de budget ;
- aucune mutation d’état d’agent ;
- aucune permission LIVE.

Les recommandations restent informatives.

## Réel vs contrefactuel

Les données réalisées sont marquées `PAPER_EXECUTED`.

Les résultats hypothétiques utilisent `CounterfactualOutcome` avec `COUNTERFACTUAL` et sont conservés séparément dans le rapport. Un `ExecutionRecord` refuse explicitement toute donnée contrefactuelle afin qu’un résultat simulé ne puisse jamais entrer dans les métriques réalisées.

Cette frontière prépare les futurs SHADOW twins et tests d’ablation sans les implémenter dans Batch 10.

## Exports

Sans nouvelle dépendance :

- `report_to_dict()` ;
- `report_to_json()` ;
- `agent_metrics_to_csv()`.

Les valeurs `Decimal`, enums, timestamps et statuts d’indisponibilité sont sérialisés de manière déterministe et testable.

## Limites volontaires

Ce lot n’ajoute pas :

- LIVE ;
- Live Broker ;
- exchange réel ;
- profils Conservative / Balanced / Aggressive parallèles ;
- SHADOW twins ;
- Rio ;
- Denver ;
- Dashboard ;
- Recruitment Engine ;
- promotion ou désactivation automatique d’agent ;
- réputation multidimensionnelle complète ;
- ablation complète ;
- attribution marginale ;
- nouvelles règles de risque ;
- nouvelle dépendance.
