# Changelog — Batch 19e Step 1

## Added

- `app/recruitment/api.py`
  - `RecruitmentApiCapabilities`
  - `RecruitmentApiContractVersion`
  - `get_recruitment_api_capabilities()`
- `app/api/routes/recruitment.py`
  - `GET /api/recruitment/capabilities`
- tests API/export/boundary Recruitment.

## Changed

- `app/recruitment/__init__.py` exporte la surface API publique.
- `app/api/router.py` enregistre le router Recruitment.

## Safety

- API Recruitment GET-only ;
- aucun endpoint de transition ou promotion ;
- aucun registre modifié ;
- aucun Risk Engine modifié ;
- aucune dépendance LIVE ;
- `operator_authorization_required=True` reste explicite.
