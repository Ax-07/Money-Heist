# Batch 15 — Preflight LIVE déterministe

## But

Le preflight répond uniquement :

```text
READY
ou
BLOCKED
```

Chaque contrôle interne est :

```text
PASS
BLOCKED
UNKNOWN
```

`UNKNOWN` est toujours bloquant. Il n'existe aucun "best effort" dans le chemin LIVE.

## Séquence opérationnelle

```text
LIVE_DISABLED
  ↓ opérateur demande un preflight
LIVE_PREFLIGHT
  ↓ toutes les vérifications = PASS
READY
  ↓ confirmation opérateur exacte dans le même processus runtime
LIVE_ARMED
```

L'état `LIVE_ARMED` n'est jamais persisté. Un redémarrage recommence à `LIVE_DISABLED`.

## Barrières système vérifiées

- `app_env=production` ;
- `runtime_mode=LIVE` ;
- environnement explicite `kraken_spot_eur` ;
- `live_system_id` explicite ;
- système `balanced_v1` uniquement ;
- cible non-SHADOW ;
- `RiskProfile` Balanced complet, sans inventer de limites ;
- kill switch compatible avec les nouvelles entrées ;
- SQLite/SQLAlchemy durable accessible ;
- audit durable accessible ;
- credentials présents à la frontière Kraken uniquement ;
- permissions de clé connues et exactement minimales ;
- aucune permission retrait/adresse de retrait ;
- Market Data/metadata/contraintes fraîches et valides ;
- source `kraken_spot` ;
- quote EUR ;
- univers strict BTC/EUR, ETH/EUR, SOL/EUR ;
- réconciliation de la session terminée ;
- aucun ordre LIVE ambigu non résolu.

## Barrières par ordre

Immédiatement avant l'`OrderIntent` :

- armement opérateur actif dans ce processus ;
- `RiskDecision.is_authorized` vrai (`APPROVED` ou `RESIZED`) ;
- `RiskDecision.proposal_id` cohérent ;
- proposition non expirée ;
- `LONG` uniquement pour une nouvelle entrée Spot ;
- `balanced_v1` uniquement ;
- symbole allowlisté ;
- profil Balanced toujours complet ;
- kill switch toujours clear ;
- réconciliation toujours valide ;
- Market Data/metadata/contraintes toujours valides.

Le broker Batch 14 réapplique ensuite ses propres contrôles d'intent, quantité, min notional, qty step, expiration et idempotence.

## Reason codes principaux

Configuration :
- `APP_ENV_NOT_PRODUCTION`
- `RUNTIME_MODE_NOT_LIVE`
- `LIVE_ENVIRONMENT_NOT_EXPLICIT`
- `LIVE_SYSTEM_NOT_EXPLICIT`
- `LIVE_SYSTEM_NOT_BALANCED`
- `TARGET_SYSTEM_IS_SHADOW`

Risque / sécurité :
- `RISK_PROFILE_UNKNOWN`
- `RISK_PROFILE_NOT_BALANCED`
- `RISK_PROFILE_INCOMPLETE`
- `KILL_SWITCH_UNKNOWN`
- `KILL_SWITCH_BLOCKS_NEW_TRADES`

Persistance / audit :
- `PERSISTENCE_UNKNOWN`
- `PERSISTENCE_UNAVAILABLE`
- `AUDIT_UNKNOWN`
- `AUDIT_UNAVAILABLE`

Kraken :
- `CREDENTIALS_UNKNOWN`
- `CREDENTIALS_MISSING`
- `API_PERMISSIONS_UNKNOWN`
- `API_PERMISSIONS_MISSING`
- `API_PERMISSION_WITHDRAWAL`
- `API_PERMISSIONS_EXCESS`

Marché :
- `MARKET_CONFIGURATION_UNKNOWN`
- `MARKET_SYMBOL_MISSING`
- `MARKET_DATA_UNKNOWN`
- `MARKET_DATA_STALE`
- `MARKET_METADATA_STALE`
- `MARKET_STATUS_INVALID`
- `MARKET_SOURCE_INVALID`
- `MARKET_NOT_SPOT_EUR`
- `MARKET_CONSTRAINTS_INVALID`

Réconciliation :
- `RECONCILIATION_UNKNOWN`
- `RECONCILIATION_REQUIRED`
- `UNRESOLVED_LIVE_ORDERS`

Ordre :
- `RISK_DECISION_NOT_AUTHORIZED`
- `RISK_DECISION_MISMATCH`
- `ORDER_STALE`
- `ORDER_SHORT_NOT_SUPPORTED`
- `ORDER_SYSTEM_MISMATCH`
- `ORDER_SYMBOL_NOT_ALLOWLISTED`
- `OPERATOR_ARM_REQUIRED`

## Permissions Kraken exactes

Le preflight utilise `POST /0/private/GetApiKeyInfo` et ne journalise jamais le champ `apiKey` renvoyé par Kraken.

Set attendu :

```text
query-funds
query-open-trades
query-closed-trades
modify-trades
close-trades
```

Tout extra est bloquant selon le principe de moindre privilège.

Référence officielle : https://docs.kraken.com/api/docs/rest-api/get-api-key-info
