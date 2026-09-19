# Batch 19b — Step 1 — Candidate Evaluation Campaign Plan

## Objectif

Définir un plan déterministe et immuable de comparaison **baseline vs candidate** sans encore exécuter de replay.

Le plan réutilise `BacktestRun`, `BacktestConfig` et `BacktestPeriodRole` du Batch 16. Les deux twins partagent le même dataset, la même période et la même configuration matérielle ; le variant candidat ajoute uniquement l'identité d'évaluation du candidat et les métadonnées Recruitment réservées.

## Contrats ajoutés

- `RecruitmentCampaignVariantKind` (`BASELINE`, `WITH_CANDIDATE`)
- `RecruitmentCampaignVariant`
- `RecruitmentCampaignPlan`
- `candidate_runtime_agent_id()`
- `build_recruitment_campaign()`

## Invariants

- le candidat n'est pas ajouté à `AgentRegistry` ;
- `candidate:<recruitment_id>` est une identité d'évaluation uniquement ;
- aucun Risk Engine, broker LIVE ou service d'exécution n'est importé ;
- aucun replay n'est lancé par ce step ;
- `DESIGN`, `VALIDATION` et `OOS` restent explicitement distincts ;
- la baseline `system_id` doit correspondre au `BacktestRun` source ;
- les critères de succès prédéfinis participent à l'identité de campagne ;
- les clés Recruitment ajoutées à `execution_assumptions` sont réservées et toute collision échoue ;
- `execute=False`, `auto_apply=False`, `registry_mutation=False`, `live_authority=False`.

## Validation

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Ne pas commit/push avant validation opérateur.
