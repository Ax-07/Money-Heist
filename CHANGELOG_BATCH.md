# Money Heist — CHANGELOG Batch 10 — Evaluation

## Base

- commit requis : `087183154dcd606f6e4977f6f738634fbc947112` ;
- Batch 09 — Pipeline PAPER complet ;
- 190 tests existants avant intégration.

## Ajouté

### Couche Evaluation déterministe

- `EvaluationSource` immutable et reconstruisible ;
- `EvaluationService` sans dépendance FastAPI/dashboard ;
- adaptateurs en lecture seule pour les contrats réels Batch 06 et Batch 09 ;
- reconstruction de trace depuis `PaperPipelineResult` ou les événements d'audit Batch 09 ;
- séparation forte `PAPER_EXECUTED` / `COUNTERFACTUAL` ;
- conservation des IDs opportunité, proposition, décision risque, ordre et fill ;
- conservation des `system_id`, prompt versions, modèles et routes disponibles.

### Métriques trading

- PnL réalisé aux prix de fill ;
- frais ;
- slippage séparé lorsqu’il est reconstructible ;
- PnL brut avant coûts lorsqu’il est reconstructible ;
- Trading Net réalisé ;
- PnL non réalisé avec mark ;
- Trading Net mark-to-market ;
- exposition brute ;
- nombre d’ordres/fills/trades clôturés/positions ;
- LONG et SHORT ;
- win rate ;
- profit factor ;
- expectancy ;
- drawdown absolu et relatif sur historique d’equity suffisant ;
- statuts explicites `UNAVAILABLE` / `UNBOUNDED` plutôt que valeurs inventées.

### Coûts IA

- coût total ;
- coût par agent ;
- coût par modèle ;
- coût par route ;
- coût par opportunité ;
- coût par décision Risk Engine ;
- coût par trade PAPER exécuté ;
- coût moyen par opportunité/décision/trade lorsque calculable ;
- conservation explicite des coûts non attribuables.

### Métriques agents V1

- appels logiques ;
- tentatives ;
- coût total/moyen ;
- latence moyenne si disponible ;
- fréquence de participation ;
- stance ;
- confiance si disponible ;
- fréquence de désaccord lorsque comparable ;
- décisions finales associées ;
- prompt versions ;
- modèles ;
- routes.

### Economie IA et Lisbon

- `Economic Net = Trading Net - coût IA` ;
- `SelfFundingRatio = Trading Net / coût IA` ;
- cas coût IA nul géré par `ZERO_AI_COST` et `None`, sans infini artificiel ;
- rapport Lisbon V1 déterministe et read-only ;
- recommandations non contraignantes ;
- aucun accès au Risk Engine, au broker, au budget dur ou à la mutation d’état agent.

### Exports

- structures Python ;
- JSON ;
- CSV métriques agents ;
- aucune nouvelle dépendance.

## Frontières garanties

- aucune nouvelle fonctionnalité LIVE ;
- aucun exchange réel ;
- aucune modification des règles Risk Engine ;
- aucune dépendance du pipeline PAPER vers Evaluation ;
- une erreur Evaluation ne détruit pas les données source déjà produites et le trading reste reconstruisible ;
- aucune donnée contrefactuelle n’entre dans les métriques PAPER réalisées ;
- aucun SelfFundingRatio ne peut modifier le risque ;
- aucun changement automatique de budget ou d’état d’agent ;
- aucun système SHADOW Batch 11 implémenté prématurément.

## Tests

25 tests Batch 10 ajoutés couvrant notamment :

- PnL PAPER, frais, slippage et Trading Net ;
- gagnants/perdants, plusieurs trades, LONG/SHORT ;
- unrealized PnL et exposition avec mark ;
- win rate, profit factor, expectancy et drawdown ;
- métriques indisponibles ;
- coûts IA total/par agent/par opportunité/par décision/par trade/modèle/route ;
- Berlin/Tokyo/Nairobi/Palermo/Professor ;
- versions de prompt, modèles et routes ;
- chaîne opportunity → analyses → proposal → risk → execution → evaluation ;
- séparation réalisé/contrefactuel ;
- Economic Net et SelfFundingRatio >1, <1, coût nul ;
- rapport Lisbon et frontières d’autorité ;
- absence de dépendance inverse depuis le pipeline PAPER ;
- reconstruction après erreur de reporting Evaluation ;
- isolation des positions par `system_id` ;
- absence de nouvelle capacité LIVE.

Total attendu après intégration : **215 tests**.

## Dépendances / migrations / configuration

- nouvelle dépendance : aucune ;
- migration : aucune ;
- variable d’environnement : aucune ;
- secret : aucun.
