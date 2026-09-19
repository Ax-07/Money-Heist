# Batch 21b — Step 2 — Reservation Ledger Foundation

Baseline attendue : `7b00d4c feat(portfolio): add static allocation policy contracts`.

## Objectif

Ajouter un ledger déterministe de réservation des capacités déjà définies par la politique
statique du Batch 21b Step 1, sans modifier le Risk Engine, le Paper Broker, le pipeline
PAPER, Task Force, Recruitment, AgentRegistry ou LIVE.

## Règles de sécurité

- le ledger n'est ni un Risk Engine ni une autorité LIVE ;
- les montants de réservation sont fournis explicitement par l'appelant et ne sont jamais
  calculés ou inférés par ce module ;
- les plafonds par crew restent ceux de `MasterAllocationPolicy` ;
- le capital Master global empêche le double-spend entre crews dont les enveloppes se
  chevauchent ;
- aucun plafond global de risque ouvert ou d'exposition brute n'est inventé ;
- l'ouverture V1 du ledger exige un snapshot Master `AVAILABLE`, entièrement observable,
  flat, avec `cash_balance == equity` ;
- un snapshot non-flat doit être réconcilié explicitement dans une étape ultérieure ;
- les requêtes sont idempotentes par `request_id` + fingerprint ;
- une réutilisation du même `request_id` avec un autre payload échoue ;
- une réservation `RESERVED` peut devenir `COMMITTED` puis `RELEASED`, ou être libérée
  directement ;
- `RESERVED` et `COMMITTED` consomment la capacité, `RELEASED` la restitue ;
- les retries de transition avec une provenance différente échouent fermés.

## Contrats ajoutés

- `ReservationRequest`
- `PortfolioReservation`
- `ReservationResult`
- `CrewReservationUsage`
- `ReservationLedgerSnapshot`
- `MasterReservationLedger`
- enums/reason codes et erreurs d'idempotence/transition associés

Le snapshot du ledger expose les montants réservés, committés et actifs ainsi que la vue
par crew pour capital, risque ouvert et exposition brute. Tous les IDs et fingerprints sont
déterministes.

## Validation

Dans le harness de construction Python 3.13 :

```text
83 passed
```

Cette validation couvre les tests Portfolio des Steps 21a 1–4, 21b Step 1 et ce Step 2.
Le dépôt complet n'est pas monté dans le harness ; la suite complète reste à exécuter dans
le checkout local du projet.

## Commandes locales

```powershell
uv run ruff check app/portfolio tests/portfolio/test_master_reservation_ledger.py
uv run pytest -q tests/portfolio/test_master_reservation_ledger.py
uv run pytest -q tests/portfolio
uv run pytest -q
git status --short
```
