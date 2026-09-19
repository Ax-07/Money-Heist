# Batch 14 — Sécurité et authentification Kraken privée

## Verrou structurel LIVE

Batch 14 ne contient **aucun mécanisme de configuration environnementale capable d'autoriser le LIVE**.

`EnvironmentKrakenCredentialProvider` ne fait que charger les credentials. `DenyAllLiveAuthorization` reste le verrou de production par défaut. Avoir `MONEY_HEIST_KRAKEN_API_KEY` et `MONEY_HEIST_KRAKEN_API_SECRET` ne suffit jamais à permettre `AddOrder`.

Une autorisation indépendante devra être composée explicitement au Batch 15. Les tests utilisent uniquement une autorisation injectée et des transports/fakes.

## Authentification Spot REST

Pour chaque appel privé :
- `API-Key` contient la clé publique ;
- `API-Sign` est calculé selon Kraken : HMAC-SHA512 de `URI path + SHA256(nonce + POST data)` avec le secret décodé en base64 ;
- `nonce` est strictement croissant par clé ;
- le secret privé n'est jamais envoyé à Kraken ;
- credentials et signature ne sont jamais écrits dans les événements d'audit.

Le test de signature utilise le vecteur officiel Kraken avec des credentials publics de documentation/fictifs.

## Permissions minimales à créer avant Batch 15

Pour la clé dédiée au trading Spot :
- lecture des fonds/balances nécessaire à la réconciliation ;
- lecture des ordres/trades ouverts ;
- lecture des ordres/trades clôturés ;
- création/modification d'ordres uniquement si nécessaire ;
- annulation/fermeture d'ordres uniquement si la politique Batch 15 l'autorise ;
- **aucun droit de retrait** ;
- aucune permission de transfert ou de funding non nécessaire.

`GetApiKeyInfo` peut être utilisé en préflight et le code Batch 14 refuse explicitement une permission dont le nom indique un droit de retrait.

## Allowlist privée

Le client privé n'expose pas de méthode générique `request(path)` ou `post(path)` publique. Les seules méthodes disponibles sont :
- `get_api_key_info` ;
- `get_balance` ;
- `get_open_orders` ;
- `get_closed_orders` ;
- `get_trades_history` ;
- `add_order` ;
- `cancel_order`.

Il n'existe aucune méthode de retrait ni transfert.

## Timeouts et retries

Les lectures privées disposent de retries bornés, backoff borné et pacing local.

Les écritures (`AddOrder`, `CancelOrder`) ne sont **jamais retryées automatiquement** après une erreur transport. Un timeout après l'envoi peut signifier que Kraken a reçu la requête ; le résultat devient donc ambigu.

## Idempotence et état ambigu

Chaque ordre LIVE utilise un `cl_ord_id` stable au format UUID. Kraken permet le filtrage par `cl_ord_id` dans `OpenOrders` et `ClosedOrders`.

Règle :

```text
AddOrder tenté
→ timeout / transport ambigu
→ RECONCILIATION_REQUIRED
→ aucune seconde soumission équivalente
→ OpenOrders(cl_ord_id)
→ ClosedOrders(cl_ord_id)
→ décision déterministe ou maintien du blocage
```

La garantie de non-duplication ne repose pas uniquement sur Kraken : l'état local bloque également un `client_order_id` marqué inconnu/ambigu.

## Persistance

Batch 14 fournit le port `LiveOrderStore` et une implémentation mémoire pour les tests. Le verrou LIVE restant structurellement fermé, cette implémentation n'est pas une autorisation de production. Le Batch 15 devra connecter une persistance/audit durable avant toute activation réelle.

## Tests privés

`tests/integration_private/` est opt-in via `MONEY_HEIST_RUN_KRAKEN_PRIVATE_TESTS=1`.

Le test privé livré est **strictement read-only** (`GetApiKeyInfo`) : aucun `AddOrder`, `CancelOrder`, modification d'ordre, retrait ou transfert n'est exécuté.
