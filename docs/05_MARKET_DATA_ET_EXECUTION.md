# Money Heist — Market Data et Exécution

**Document :** Données de marché et exécution  
**Version :** 0.2  
**Statut :** Spécification initiale

---

## 1. Objectif

Définir comment Money Heist :
- reçoit les données ;
- vérifie leur qualité ;
- les transforme en features ;
- détecte des opportunités ;
- simule des ordres ;
- exécute des ordres réels à terme.

Le choix du Market Data initial est désormais **Kraken Spot public / EUR** (ADR-019).

---

## 2. Principe de normalisation

Le code métier ne doit pas dépendre du JSON brut de l’exchange.

Chaque connecteur transforme ses données vers des modèles internes.

Exemple :

```text
ExchangePayload
    ↓
ExchangeAdapter
    ↓
NormalizedMarketData
```

---

## 3. Types de données

### V1 prioritaires
- OHLCV ;
- prix courant ;
- volume ;
- métadonnées symbole ;
- contraintes d’ordre.

### Extensions
- trades ;
- order book ;
- funding ;
- open interest ;
- liquidations.

Une source indisponible ne doit jamais être simulée par un agent.

---

## 4. MarketSnapshot

Un snapshot doit contenir :
- `snapshot_id` ;
- timestamp source ;
- timestamp de collecte ;
- symbole ;
- timeframes disponibles ;
- features calculées ;
- indicateurs de qualité ;
- source/provider.

---

## 5. Fraîcheur

Chaque type de donnée possède un seuil de fraîcheur.

Si une donnée critique est trop ancienne :
- le snapshot est marqué invalide ;
- aucune nouvelle position dépendant de cette donnée n’est autorisée.

---

## 6. Bougies

Exigences :
- ordre chronologique ;
- pas de doublons ;
- timestamp cohérent ;
- détection des trous ;
- bougie en cours distinguée des bougies closes.

Les indicateurs backtestés ne doivent pas utiliser involontairement des données futures.

---

## 7. Feature Engine

Calculs possibles :
- EMA ;
- RSI ;
- MACD ;
- ATR ;
- ADX ;
- Bollinger ;
- variation volume ;
- structure de marché ;
- distance support/résistance ;
- volatilité réalisée.

Les calculs utilisés en production doivent être identiques à ceux utilisés en backtest lorsque possible.

---

## 8. Scanner

Le scanner produit un score d’intérêt et des raisons.

Exemple :

```json
{
  "symbol": "SOLUSDT",
  "priority_score": 82,
  "triggers": [
    "volume_expansion",
    "breakout_candidate"
  ]
}
```

Ce score sert au Compute Gate.

Il ne constitue pas une recommandation de trade.

---

## 9. Réduction des tokens

Les agents reçoivent de préférence :
- features ;
- résumé de structure ;
- quelques valeurs historiques pertinentes ;
- références vers données calculées.

Eviter l’envoi systématique de centaines de bougies brutes.

---

## 10. Paper Broker

Le Paper Broker doit simuler :
- compte ;
- balance ;
- equity ;
- ordres ;
- fills ;
- positions ;
- frais ;
- slippage ;
- stops ;
- targets.

Il utilise la même interface que le Live Broker.

---

## 11. Interface Broker conceptuelle

```python
class Broker:
    async def submit_order(self, order): ...
    async def cancel_order(self, order_id): ...
    async def get_order(self, order_id): ...
    async def get_positions(self): ...
    async def get_account_state(self): ...
```

Le `ExecutionRouter` sélectionne l’implémentation.

---

## 12. Modèle de fill PAPER

Le modèle doit être configurable.

Première version possible :
- market : prix courant + slippage simulé ;
- limit : fill uniquement si le marché traverse le prix ;
- frais appliqués selon configuration.

Les hypothèses doivent être documentées et ne pas prétendre reproduire parfaitement la microstructure réelle.

---

## 13. Slippage

Le slippage doit être :
- non nul dans les simulations réalistes ;
- configurable ;
- éventuellement dépendant de l’actif et de la volatilité plus tard.

Les résultats de backtest sans slippage doivent être identifiés comme tels.

---

## 14. Frais

Le système stocke :
- maker fee ;
- taker fee ;
- funding si dérivés ;
- autres coûts pertinents.

Les valeurs doivent provenir de la configuration ou du connecteur, pas d’un LLM.

---

## 15. Contraintes symbole

Pour chaque paire :
- tick size ;
- step size ;
- min quantity ;
- min notional ;
- precision.

Le Risk Engine et le broker utilisent la même source de vérité.

---

## 16. Live Broker

Conditions :
- adaptateur spécifique exchange ;
- authentification isolée ;
- droits de retrait désactivés ;
- client order id ;
- gestion des timeouts ;
- retries limités et idempotents ;
- réconciliation périodique.

---

## 17. Réconciliation

La base locale n’est jamais supposée être la vérité absolue sur un ordre LIVE.

Le système doit comparer :
- ordre local ;
- ordre exchange ;
- fills exchange ;
- position exchange.

Toute divergence déclenche un événement d’alerte.

---

## 18. Double exécution

Protection requise :
- `client_order_id` unique ;
- idempotence ;
- état transactionnel ;
- interdiction de renvoyer un ordre après timeout sans vérifier l’état précédent.

---

## 19. Websocket et REST

Architecture possible :
- websocket pour flux temps réel ;
- REST pour bootstrap et réconciliation.

La stratégie exacte dépendra de l’exchange choisi.

---

## 20. Pannes réseau

Comportement :
- marquer les données comme potentiellement stale ;
- suspendre les nouvelles entrées ;
- reconnecter avec backoff ;
- restaurer l’état ;
- réconcilier avant reprise.

---

## 21. Univers initial

Pour le Batch 13, l'adaptateur Kraken Spot utilise les symboles canoniques :
- `BTC/EUR` ;
- `ETH/EUR` ;
- `SOL/EUR`.

Ce choix fixe le premier univers de **Market Data réel**. Il ne constitue pas une activation LIVE.

### 21.1 Décision Batch 13 — Kraken Spot public

Les endpoints REST publics sont utilisés sans clé API pour :
- le dernier trade horodaté, utilisé comme prix courant et source de fraîcheur ;
- les bougies OHLC ;
- les métadonnées `AssetPairs`.

La dernière bougie OHLC renvoyée par Kraken est considérée comme la bougie courante et reste explicitement `is_closed=False`.

Les métadonnées disponibles sont normalisées vers un modèle interne distinct du payload Kraken. Elles incluent notamment :
- `tick_size` ;
- précision prix ;
- précision quantité ;
- `ordermin` → quantité minimale ;
- `costmin` → notional minimal ;
- pas de quantité dérivé de la précision quantité.

La projection vers le `MarketConstraints` existant transmet uniquement les champs déjà supportés par le Risk Engine. `tick_size` et les précisions restent des métadonnées de marché destinées notamment au futur broker.

Les timeframes de production et les seuils numériques de fraîcheur ne sont pas fixés ici : ils restent injectés explicitement par configuration.

---

## 22. Timeframes

Les timeframes ne sont pas encore figés.

Le système doit permettre plusieurs timeframes par symbole sans changer les interfaces métier.

---

## 23. Données historiques

Le système doit pouvoir :
- importer ;
- stocker ;
- rejouer.

Objectifs :
- backtest ;
- replay ;
- tests de scanner ;
- tests d’agents ;
- comparaison de versions.

---

## 24. Reproductibilité

Une décision doit pouvoir référencer :
- le snapshot exact ;
- les features ;
- le code/version des indicateurs ;
- les prompts ;
- les sorties agents.

---

## 25. Critères d’acceptation

Avant LIVE :
- données stale détectées ;
- normalisation testée ;
- contraintes symbole respectées ;
- paper fees fonctionnels ;
- slippage fonctionnel ;
- double ordre impossible dans les tests ;
- réconciliation fonctionnelle ;
- erreur exchange bloque proprement l’entrée.


---

## 26. Addendum Batch 16 — données historiques et modèle d’exécution

Les datasets utilisés par le backtest sont content-addressed : tri chronologique, timestamps UTC, contrôle des doublons, cohérence OHLCV et hash stable.

La politique d’exécution historique V1 est déterministe et conservatrice :
- décision à la clôture N, protection active seulement sur les bougies futures ;
- stop + target touchés dans la même bougie : STOP_FIRST ;
- gap défavorable au-delà du stop : référence = open, puis slippage market PaperBroker ;
- gap favorable au-delà du target : fill plafonné au target ;
- target V1 : premier target, sortie complète ;
- frais maker/taker et slippage proviennent de la configuration PaperBroker/backtest.

Le modèle d’exécution possède une version explicite dans `BacktestConfig`. Une modification matérielle des hypothèses d’exécution doit changer cette version ou les `execution_assumptions` afin de modifier le `run_id`.
