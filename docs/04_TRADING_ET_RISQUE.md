# Money Heist — Trading et Gestion du Risque

**Document :** Trading et risque  
**Version :** 0.1  
**Statut :** Spécification initiale  
**Références :** `01_PROJECT_MASTER.md`, `02_ARCHITECTURE.md`

---

## 1. Objectif

Définir la séparation entre :
- idée de trade ;
- proposition IA ;
- risque autorisé ;
- exécution ;
- gestion de position ;
- sécurité portefeuille.

Ce document ne fixe pas encore les valeurs numériques finales du profil Balanced.

---

## 2. Principe central

Une opinion de la crew devient une **TradeProposal**.

Une `TradeProposal` n’est jamais un ordre.

```text
Analyse IA
   ↓
TradeProposal
   ↓
Risk Engine
   ↓
AuthorizedTrade
   ↓
Broker
```

---

## 3. TradeProposal

Champs conceptuels :

```json
{
  "system_id": "balanced_v1",
  "symbol": "BTCUSDT",
  "side": "LONG",
  "confidence": 0.74,
  "entry_plan": {},
  "stop_plan": {},
  "target_plan": {},
  "expected_rr": 2.1,
  "thesis": [],
  "invalidation": [],
  "market_regime": "string",
  "expires_at": "timestamp",
  "source_snapshot_id": "id"
}
```

Le montant final à engager n’est pas nécessairement décidé par l’IA.

---

## 4. Risk Engine

Le Risk Engine calcule ou valide :
- exposition ;
- risque monétaire ;
- quantité ;
- levier ;
- stop ;
- limites cumulées.

Décisions possibles :

```text
APPROVE
REJECT
RESIZE
```

Toute décision contient un `reason_code`.

---

## 5. Constitution de risque

Ces paramètres sont externes aux agents :
- `max_risk_per_trade_pct` ;
- `max_daily_loss_pct` ;
- `max_drawdown_pct` ;
- `max_portfolio_risk_pct` ;
- `max_positions` ;
- `max_leverage` ;
- `min_expected_rr` si activé ;
- `max_correlated_exposure` ;
- règles de cooldown ;
- kill switch.

---

## 6. Capital initial

Capital LIVE prévu pour le prototype :

**100 €**

Conséquence :
- petites tailles d’ordres ;
- attention aux minimums exchange ;
- frais proportionnellement importants ;
- nécessité d’éviter l’overtrading.

Le capital ne doit pas être divisé entre plusieurs crews LIVE dans la première phase.

---

## 7. Profils de risque

### 7.1 Conservative / Vault

Caractéristiques :
- faible risque par trade ;
- faible exposition simultanée ;
- fréquence réduite ;
- exigences de confirmation élevées ;
- levier nul ou très faible.

### 7.2 Balanced

Candidat initial LIVE.

Caractéristiques :
- risque contrôlé ;
- nombre de trades raisonnable ;
- compromis entre fréquence et sélectivité.

### 7.3 Aggressive / Tokyo

Initialement SHADOW.

Caractéristiques :
- plus d’opportunités ;
- plus grande tolérance à la volatilité ;
- risque supérieur mais plafonné.

Le profil Aggressive ne signifie jamais “risque illimité”.

---

## 8. Position sizing

Méthode conceptuelle principale :

```text
risque_monétaire =
equity × risque_pct

distance_stop =
|entrée - stop|

quantité =
risque_monétaire / distance_stop
```

Puis appliquer :
- précision de quantité ;
- min notional ;
- max exposure ;
- limites exchange ;
- frais estimés.

Le sizing final appartient au Risk Engine.

---

## 9. Risque portefeuille

Le système doit distinguer :
- risque par trade ;
- risque simultané ;
- exposition directionnelle ;
- corrélation entre actifs.

Exemple :

```text
LONG BTC
LONG ETH
LONG SOL
```

ne constitue pas forcément trois risques indépendants.

Une V1 peut utiliser une règle prudente simplifiée avant d’introduire une matrice de corrélation avancée.

---

## 10. Daily Loss Limit

Lorsque la perte journalière atteint le seuil configuré :
- aucune nouvelle position ;
- gestion des positions existantes selon règles prévues ;
- événement sécurité ;
- reprise selon politique configurée.

Un agent ne peut pas demander d’exception.

---

## 11. Drawdown

Le système suit au minimum :
- equity peak ;
- drawdown courant ;
- drawdown maximal.

Des paliers peuvent exister :
- warning ;
- reduced-risk ;
- stop-new-trades ;
- kill.

Les seuils exacts seront définis avant LIVE.

---

## 12. Levier

Pour le premier prototype, la direction du projet est :
- aucun levier ou levier minimal.

Si des dérivés sont retenus :
- le levier effectif doit être borné ;
- les règles de liquidation doivent être prises en compte ;
- la marge doit être surveillée ;
- le Risk Engine reste l’autorité.

---

## 13. Stop Loss

Toute position LIVE nécessitant un stop selon le profil doit avoir un plan d’invalidation clair.

Le système doit distinguer :
- stop logique ;
- stop d’exécution ;
- stop de sécurité.

Le Risk Engine peut rejeter :
- stop trop éloigné ;
- stop absent ;
- stop incompatible avec la taille minimale ;
- stop donnant un risque supérieur au maximum.

---

## 14. Take Profit et sorties

La V1 doit permettre :
- target unique ;
- sorties partielles plus tard ;
- trailing stop plus tard ;
- sortie pour invalidation ;
- sortie de sécurité.

Les stratégies complexes ne sont pas prioritaires avant la fiabilité de l’exécution.

---

## 15. Expiration du signal

Toute proposition possède une durée de validité.

Une proposition devenue obsolète ne peut pas être exécutée.

Le broker vérifie la fraîcheur avant soumission.

---

## 16. Risque de frais

Le système doit estimer :
- trading fees ;
- spread ;
- slippage ;
- funding si applicable.

Un trade peut être rejeté si :
- l’espérance attendue est trop faible par rapport aux coûts.

---

## 17. Mode SHADOW

Les profils SHADOW utilisent :
- mêmes règles de proposition ;
- leur propre Risk Engine logique ;
- leur propre capital virtuel ;
- mêmes modèles de frais/slippage.

Ils ne peuvent pas générer un `LiveOrder`.

---

## 18. Passage PAPER → LIVE

Conditions recommandées :
- tests unitaires Risk Engine ;
- tests de propriétés sur sizing ;
- simulation de pertes ;
- kill switch ;
- test de double ordre ;
- test de timeout ;
- validation des minimums exchange ;
- période paper suffisante ;
- audit des décisions.

---

## 19. Kill Switch

Le kill switch doit pouvoir :
- bloquer immédiatement les nouvelles positions ;
- désactiver l’orchestration IA ;
- éventuellement déclencher la politique configurée pour les positions ouvertes.

Il doit être accessible sans dépendre d’un LLM.

---

## 20. Interdictions

La crew ne peut pas :
- augmenter son plafond de risque ;
- désactiver le Risk Engine ;
- augmenter le levier maximal ;
- ignorer une perte journalière ;
- transférer le budget IA vers le capital ;
- modifier le capital de référence arbitrairement ;
- créer une position hors du broker autorisé.

---

## 21. Tests obligatoires

Au minimum :
- sizing correct ;
- rejet si stop invalide ;
- rejet si risque trop élevé ;
- rejet si daily loss atteint ;
- rejet si drawdown atteint ;
- limite du nombre de positions ;
- exposition corrélée ;
- ordre expiré ;
- mode SHADOW incapable de LIVE ;
- kill switch.

---

## 22. Décisions ouvertes

Avant activation LIVE :
- valeurs exactes Balanced ;
- spot ou dérivés ;
- levier éventuel ;
- type de stop initial ;
- limites de positions ;
- politique de reprise après daily stop ;
- gestion des positions lors d’un kill switch.

Ces décisions seront consignées dans `10_DECISIONS_ET_CHANGELOG.md`.
