# Batch 19e — Step 1 — Public Exports & Read-only Recruitment API

Baseline de référence : `96b2288` + Batch 19a/19b/19c/19d overlays validés localement.

## Objectif

Exposer proprement les contrats publics du Recruitment Engine sans ajouter d'autorité opérationnelle.

Ce step ajoute :

- `app.recruitment.api.RecruitmentApiCapabilities` ;
- `app.recruitment.api.RecruitmentApiContractVersion` ;
- `get_recruitment_api_capabilities()` ;
- l'endpoint `GET /api/recruitment/capabilities` ;
- l'enregistrement du router Recruitment dans `app/api/router.py` ;
- un audit des exports publics `app.recruitment.__all__`.

## Frontière de sécurité

L'API Recruitment est volontairement `ADVISORY_READ_ONLY` :

- aucun POST/PUT/PATCH/DELETE Recruitment ;
- aucune mutation `AgentRegistry` ;
- aucune application de transition lifecycle ;
- aucune promotion appliquée ;
- aucune autorité LIVE ;
- autorisation opérateur toujours requise.

L'endpoint capabilities ne lit ni n'écrit un store Recruitment. Il publie uniquement les contrats, métriques, états et garde-fous déjà définis par Batch 19.

## Validation demandée

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Ne pas commit/push avant validation. Ne pas utiliser `git add -A`.
