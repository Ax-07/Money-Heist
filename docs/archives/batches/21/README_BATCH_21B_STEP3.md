# Batch 21b — Step 3 — Reservation Reconciliation & Snapshot Bridge

Baseline attendue: `6e13ea0 feat(portfolio): add reservation ledger foundation`.

## Objectif

Ajouter une couche read-only qui compare un `ReservationLedgerSnapshot` à un
`MasterPortfolioSnapshot` observé, sans muter le ledger et sans créer de nouvelle autorité
Risk, broker, admission ou LIVE.

## Règle de comparaison V1

Seules les dimensions réellement comparables sont réconciliées par crew:

- `open_risk_amount` observé vs `committed_open_risk_amount`;
- `gross_exposure_amount` observé vs `committed_gross_exposure_amount`.

Le capital réservé/committé reste visible comme provenance comptable mais n'est pas comparé à
l'equity ou au cash courants: ces valeurs ne représentent pas la même chose et aucune
équivalence artificielle n'est introduite.

Les montants encore `RESERVED` ne sont pas attendus dans l'exposition marché. Seuls les
montants `COMMITTED` constituent la référence d'exposition attendue.

## Statuts

- `CONSISTENT`: observé == committed sur risque et exposition brute;
- `PENDING`: committed > observé, compatible avec une observation/fill encore partiel;
- `INCONSISTENT`: observé > committed sur au moins une dimension;
- `UNAVAILABLE`: réconciliation impossible ou source indisponible.

## Garde-fous

La réconciliation échoue fermée si:

- le Master Portfolio diffère;
- le fingerprint de policy diffère du fingerprint scellé dans le ledger;
- la membership courante diffère de la policy, y compris `membership_ref`;
- l'ensemble des crews du ledger diffère;
- le ledger contient un événement postérieur au snapshot observé.

Step 3 ne reconstruit pas un historique "as-of" à partir d'un ledger courant.

## Fichiers

- `app/portfolio/reconciliation.py`
- `app/portfolio/__init__.py`
- `tests/portfolio/test_master_reservation_reconciliation.py`
- `README_BATCH_21B_STEP3.md`

## Hors périmètre

- aucune mutation automatique de réservation;
- aucun release/commit automatique;
- aucun Master Risk Gate;
- aucune décision d'admission;
- aucune intégration PaperTradingPipeline;
- aucune intégration LIVE;
- aucune allocation adaptative;
- aucune corrélation statistique.

## Validation attendue

```powershell
uv run ruff check app/portfolio tests/portfolio/test_master_reservation_reconciliation.py
uv run pytest -q tests/portfolio/test_master_reservation_reconciliation.py
uv run pytest -q tests/portfolio
uv run pytest -q
git status --short
```
