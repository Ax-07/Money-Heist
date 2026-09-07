# CHANGELOG — Batch 15 — Activation LIVE 100 €

## Baseline

- Dépôt : `Ax-07/Money-Heist`
- Commit cible post-Batch 14 : `10622f0da59cbb5ba03a66dcdf2bfeba919baf53`
- Message : `feat(live): complete Batch 14 secure Live Broker`

## Objectif

Ajouter la couche d'activation opérationnelle fail-closed autour du Live Broker Kraken Spot livré au Batch 14, sans envoyer d'ordre réel pendant le développement ou les tests.

## Livré

- configuration LIVE explicitement éligible uniquement en environnement `production` + `kraken_spot_eur` + `live_system_id` ;
- présence des credentials Kraken toujours insuffisante pour activer ou armer le LIVE ;
- `DenyAllLiveAuthorization` conservé comme défaut sûr ;
- état opérationnel explicite : `LIVE_DISABLED → LIVE_PREFLIGHT → LIVE_ARMED` ;
- armement opérateur éphémère, non persisté et perdu à chaque redémarrage ;
- preflight déterministe `READY/BLOCKED` avec contrôles `PASS/BLOCKED/UNKNOWN` ;
- `UNKNOWN` toujours bloquant ;
- Balanced uniquement pour `balanced_v1` ;
- Kraken Spot / EUR uniquement : BTC/EUR, ETH/EUR, SOL/EUR ;
- SHORT d'entrée LIVE toujours refusé ; aucune marge/dérivé/levier ajouté ;
- contrôle exact des permissions Kraken via `GetApiKeyInfo` ;
- refus de toute permission supplémentaire par rapport au minimum requis pour le chemin Batch 14 ;
- refus explicite des permissions de retrait/adresses de retrait ;
- preflight d'ordre immédiatement avant création/soumission d'un `OrderIntent` ;
- persistance SQLite/SQLAlchemy des ordres LIVE, états de soumission, txid, fills, audit et état de réconciliation ;
- migration Alembic `0002_live_activation_state.py` ;
- état de sécurité LIVE durable (`live_safety_state`) : absence = UNKNOWN/BLOCKED ;
- commandes opérateur auditées `status`, `clear`, `stop-new-trades`, `emergency` ;
- réconciliation obligatoire au démarrage/perte de connexion avant nouvelle entrée ;
- détection des ordres exchange ouverts inattendus ;
- persistance des fills connus ;
- capability Kraken privée READ-ONLY pour la commande de preflight ;
- commande opérateur `uv run python -m app.trading.live.preflight_cli` ;
- script PowerShell `scripts/live_preflight.ps1` ;
- nouveaux tests Batch 15 hors réseau par défaut ;
- checklist et runbooks d'exploitation.

## Invariants préservés

- aucun changement du Risk Engine ;
- aucune nouvelle valeur de risque ;
- aucun changement numérique des profils Conservative / Balanced / Aggressive ;
- `SelfFundingRatio` n'intervient pas dans le risque ;
- aucun ordre réel dans la suite de tests ;
- aucun retry automatique d'`AddOrder` ou `CancelOrder` après issue ambiguë ;
- aucune clé/secrète dans le dépôt ou le ZIP ;
- aucun agent ne reçoit de credentials ou de pouvoir d'activation ;
- Dashboard toujours read-only concernant l'exécution.

## Bloqueurs réels conservés au lieu d'être inventés

Le dépôt post-Batch 14 laisse volontairement le profil Balanced sans valeurs constitutionnelles numériques par défaut. Le preflight Batch 15 retourne donc `RISK_PROFILE_INCOMPLETE` tant qu'un profil Balanced complet, validé hors du code de ce lot, n'est pas fourni explicitement.

Le Batch 13 ne fige pas non plus les timeframes de production ni les seuils numériques de fraîcheur Market Data. Le preflight retourne `MARKET_CONFIGURATION_UNKNOWN` tant que ces paramètres ne sont pas fournis explicitement.

Ces deux points sont des blocages d'activation, pas des invitations à inventer des valeurs.
