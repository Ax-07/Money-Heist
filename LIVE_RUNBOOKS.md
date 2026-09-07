# Batch 15 — Runbooks LIVE

## 1. Arrêt / stop nouvelles entrées

1. Déclencher `uv run python -m app.trading.live.safety_cli stop-new-trades --reason "..."` ou le mode `emergency`; l’état est durable.
2. Désarmer l'état LIVE du processus ; ne pas tenter de "finir" une opportunité en cours.
3. Ne pas effacer les ordres/fills/audits locaux.
4. Observer Kraken en lecture seule et réconcilier.
5. Tout redémarrage repart `LIVE_DISABLED` et exige un nouveau preflight.

La gestion d'une position déjà ouverte reste gouvernée par la politique existante du projet ; Batch 15 n'invente pas une règle de liquidation/stop.

## 2. Timeout / ordre inconnu après tentative de soumission

Règle constitutionnelle : **ne jamais renvoyer automatiquement un ordre équivalent**.

```text
AddOrder tenté
→ timeout/transport ambigu
→ RECONCILIATION_REQUIRED
→ blocage nouvelles entrées
→ OpenOrders / ClosedOrders via cl_ord_id
→ TradesHistory / fills
→ résolution déterministe
```

Si l'ordre n'est pas retrouvable de manière déterministe : rester bloqué. Ne pas transformer l'absence de réponse en preuve que l'ordre n'existe pas.

## 3. Crash après persistance `NEW`

`NEW` est écrit durablement avant l'appel `AddOrder`. Après crash, il doit être traité comme potentiellement ambigu :

1. aucun nouvel ordre ;
2. réconciliation Kraken par `cl_ord_id` ;
3. si trouvé : lier txid, état et fills ;
4. si non trouvé : conserver le blocage jusqu'à résolution explicite ;
5. ne jamais supprimer le record pour "débloquer".

## 4. Ordre Kraken ouvert inattendu

Si `OpenOrders` contient un ordre non représenté dans l'état LIVE durable :

1. preflight `BLOCKED` ;
2. ne pas soumettre de nouvel ordre ;
3. identifier si l'ordre est manuel, ancien ou issu d'un incident ;
4. observer son txid/cl_ord_id/fills ;
5. décider humainement de l'action ;
6. réconcilier et auditer avant toute reprise.

## 5. Incohérence balance / fill

1. bloquer les nouvelles entrées ;
2. conserver une copie de la base et des logs/audits ;
3. relire balances, ordres ouverts/fermés et TradesHistory Kraken ;
4. comparer txid, cl_ord_id, quantité exécutée, prix et frais ;
5. ne pas éditer silencieusement la base pour la faire correspondre ;
6. journaliser toute correction opérateur ;
7. nouveau preflight seulement après état cohérent.

## 6. Perte de connexion

1. marquer la réconciliation comme requise ;
2. bloquer les nouvelles entrées ;
3. laisser les retries bornés uniquement aux lectures idempotentes ;
4. aucun retry aveugle d'`AddOrder`/`CancelOrder` ;
5. après retour réseau, exécuter la réconciliation de session ;
6. re-preflight avant reprise.

## 7. Base SQLite indisponible / audit impossible

1. bloquer les nouvelles entrées ;
2. ne pas utiliser `InMemoryLiveOrderStore` comme remplacement de production ;
3. restaurer la disponibilité de la base ;
4. réconcilier Kraken avec l'état durable ;
5. preflight complet avant reprise.

## 8. Clé Kraken compromise

1. arrêter/désarmer immédiatement le runtime ;
2. bloquer les nouvelles entrées ;
3. révoquer la clé compromise côté Kraken ;
4. vérifier l'activité du compte et les ordres/fills ;
5. créer une nouvelle clé dédiée avec le set minimal exact et **aucun retrait** ;
6. remplacer les secrets dans la frontière de secrets, jamais dans Git ;
7. exécuter d'abord les contrôles privés read-only ;
8. réconcilier ;
9. exécuter un nouveau preflight ;
10. ne réarmer qu'après validation humaine.

Référence Kraken sécurité : https://support.kraken.com/articles/api-key-security

## 9. Rollback logiciel Batch 15

Avant tout ordre LIVE réel : un rollback de code vers Batch 14 est possible après sauvegarde de la base.

Après toute tentative/activité LIVE : **ne pas supprimer les tables Batch 15 ni downgrader aveuglément la migration**, car elles peuvent contenir la seule trace durable nécessaire à la réconciliation. Conserver le schéma, arrêter le trading, exporter/sauvegarder la base et traiter le rollback comme une opération de récupération.
