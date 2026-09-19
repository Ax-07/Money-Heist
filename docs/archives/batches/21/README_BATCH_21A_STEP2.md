# Batch 21a — Step 2 — Master Portfolio Observation Bridge

Baseline locale attendue : `41ff2d5 feat(portfolio): add master portfolio state foundation`.

## Périmètre

Ce Step ajoute un bridge read-only entre les providers `PortfolioRiskState` existants et les
contrats immuables du Master Portfolio introduits au Step 1.

Le bridge projette uniquement, par crew :

- `open_positions` ;
- `gross_exposure_amount` ;
- `open_risk_amount`.

Il ignore explicitement l'equity locale, le day-start equity, l'equity peak, le daily PnL et
`correlated_risk_amount`. Ces champs locaux ne peuvent pas devenir du capital Master.

Le `MasterCapitalSnapshot` reste une entrée unique, explicite et autoritative. Aucune somme des
equities PAPER/SHADOW n'est effectuée.

## Fail-closed

Une absence de state, un échec de lecture ou un state structurellement invalide produit un
`CrewExposureSnapshot` `UNAVAILABLE` avec reason code stable. Aucun zéro n'est inventé.

Un provider explicitement scope à un autre `system_id` est rejeté comme erreur de câblage.

## Hors périmètre

- allocation de capital ;
- réservation/commit/release ;
- arbitrage concurrent ;
- Master Portfolio Risk Gate ;
- corrélation statistique ;
- changement du Risk Engine ;
- changement Paper Broker / PaperTradingPipeline ;
- Task Force / Recruitment / AgentRegistry ;
- LIVE.

## Validation

```powershell
uv run ruff check app/portfolio tests/portfolio/test_master_observation.py
uv run pytest -q tests/portfolio/test_master_snapshot.py tests/portfolio/test_master_observation.py
uv run pytest -q
```
