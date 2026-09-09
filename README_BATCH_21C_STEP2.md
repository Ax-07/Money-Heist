# Batch 21c — Step 2 — Deterministic Veto-Only Evaluator

Baseline attendue : `e82e9f6 feat(portfolio): add master risk gate contracts`.

## Objectif

Ajouter l'évaluateur déterministe du Master Portfolio Risk Gate sans modifier le pipeline
PAPER, le Risk Engine local, le broker ou LIVE.

Le flux V1 est :

```text
Local Risk APPROVED / RESIZED
        +
Master allocation policy
        +
Master Risk Gate policy
        +
Master Portfolio snapshot
        +
Reservation ledger snapshot
        ↓
evaluate_master_risk_gate(...)
        ↓
ADMIT / REJECT uniquement
```

## Invariants

- un rejet du Risk Engine local reste terminal ;
- aucun resize Master n'est possible ;
- `ADMIT` conserve exactement quantité, risque et notional autorisés localement ;
- la réservation candidate doit exister et être encore `RESERVED` ;
- son `system_id`, `request_ref`, risque et exposition brute doivent correspondre au candidat ;
- le gate ne mute jamais le ledger ;
- les fingerprints de policy, snapshot et ledger sont scellés dans la décision ;
- les plafonds globaux restent explicitement opérateur-owned ;
- les réservations concurrentes `RESERVED` sont comptées avant admission ;
- les engagements `COMMITTED` sont rapprochés du snapshot via la réconciliation 21b Step 3 ;
- une réconciliation `INCONSISTENT` ou `UNAVAILABLE` est fail-closed ;
- une réconciliation `PENDING` reste évaluable en utilisant `max(observé, committed) + RESERVED` ;
- aucun plafond de positions, corrélation ou concentration n'est inventé ;
- aucune autorité broker, registry ou LIVE n'est ajoutée.

## API ajoutée

- `evaluate_master_risk_gate(...)`

Deux reason codes supplémentaires rendent explicites les refus dus à la cohérence du ledger :

- `RESERVATION_RECONCILIATION_UNAVAILABLE`
- `RESERVATION_RECONCILIATION_INCONSISTENT`

## Validation locale attendue

```powershell
uv run ruff check app/portfolio tests/portfolio/test_master_risk_gate_evaluator.py
uv run pytest -q tests/portfolio/test_master_risk_gate_evaluator.py
uv run pytest -q tests/portfolio
uv run pytest -q
git status --short
```
