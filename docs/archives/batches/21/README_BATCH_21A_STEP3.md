# Batch 21a — Step 3 — Master Portfolio Fleet Observation Orchestration

Baseline locale attendue : `9f27de3 feat(portfolio): add master portfolio observation bridge`.

## Périmètre

Ce Step ajoute une orchestration read-only réutilisable au-dessus des contrats Step 1 et du bridge
Step 2. `MasterPortfolioFleetObserver` fige explicitement :

- les membres du Master Portfolio ;
- une source `PortfolioRiskState` par membre ;
- un ordre d'observation canonique par `system_id`.

À chaque observation, chaque source est lue exactement une fois au timestamp porté par le
`MasterCapitalSnapshot`, puis les `CrewExposureSnapshot` sont agrégés par le builder existant.

## Isolation des échecs

Une absence/erreur de lecture d'une crew reste localisée à cette crew via le mécanisme Step 2.
L'observation continue pour les autres crews afin de préserver leur provenance et leur état réel.
Le snapshot global reste fail-closed : si une exposition est `UNAVAILABLE`, aucun agrégat global
incomplet n'est inventé.

## Capital Master

Le fleet observer ne lit et ne somme jamais les equities locales. Le capital Master demeure
l'unique `MasterCapitalSnapshot` fourni explicitement à `observe()`.

## Hors périmètre

- allocation de capital ;
- réservation / commit / release ;
- arbitrage concurrent ;
- Master Portfolio Risk Gate ;
- corrélation statistique ;
- modification du Risk Engine ;
- modification du Paper Broker / PaperTradingPipeline ;
- Task Force / Recruitment / AgentRegistry ;
- LIVE.

## Validation

```powershell
uv run ruff check app/portfolio tests/portfolio/test_master_fleet.py
uv run pytest -q tests/portfolio/test_master_snapshot.py tests/portfolio/test_master_observation.py tests/portfolio/test_master_fleet.py
uv run pytest -q
```
