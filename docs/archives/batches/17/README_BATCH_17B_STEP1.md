# Batch 17b — Step 1 — Rio / Kraken Futures Analytics

## Objectif

Ajouter une source **réelle, publique et sans authentification** pour le spécialiste Rio,
sans modifier le Risk Engine, le Paper Broker, le Live Broker ou les secrets Kraken.

## Source

Le Step 1 consomme uniquement les endpoints publics Kraken Futures Analytics :

- `open-interest` ;
- `long-short-ratio` ;
- `funding`.

Le mapping initial est explicite :

- `BTC/EUR -> PF_XBTUSD` ;
- `ETH/EUR -> PF_ETHUSD` ;
- `SOL/EUR -> PF_SOLUSD`.

Aucun symbole dérivé n'est deviné dynamiquement.

## Liquidations

Kraken expose un analytics `liquidation-volume`, mais ce flux est un volume total.
Le contrat `RioContext v1` attend deux valeurs séparées : long et short.
Le Step 1 ne projette donc **aucune liquidation par côté** tant qu'une attribution fiable
n'est pas explicitement disponible. Les champs restent absents et sont listés dans
`missing_fields`.

## Fail-closed

- timestamp futur -> rejet ;
- métrique stale -> omission ;
- payload malformé d'une métrique -> contexte dégradé sans invention ;
- aucune métrique exploitable -> rejet ;
- contexte Rio plus récent que la décision spot -> non exposé ;
- contexte trop ancien -> non exposé ;
- un refresh plus ancien ne peut pas écraser un cache plus récent.

## Architecture

`KrakenFuturesAnalyticsProvider`
-> `DerivativesPositioningSnapshot`
-> cache `KrakenFuturesRioContextProvider`
-> `RioContext`
-> orchestration Batch 17a

Le fetch réseau reste asynchrone. L'orchestration consomme uniquement un cache synchrone,
ce qui respecte le port `SpecialistContextProvider` livré au Batch 17a.

## Tests

Les tests unitaires utilisent exclusivement un transport fake. Le smoke test réseau est
ignoré par défaut et nécessite :

```powershell
$env:RUN_KRAKEN_FUTURES_NETWORK_SMOKE="1"
uv run pytest -q tests/integration_network/test_kraken_futures_public.py
Remove-Item Env:RUN_KRAKEN_FUTURES_NETWORK_SMOKE
```

Aucun credential n'est nécessaire pour ce smoke test.
