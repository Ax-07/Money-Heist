# Batch 19d — Step 1 — Recruitment Advisory

Baseline de travail : Batch 19c validé localement avec 89 tests Recruitment.

Ce step ajoute une politique advisory déterministe qui consomme uniquement le
`RecruitmentCandidateEvidencePackage` gelé et le lifecycle Recruitment courant.

Sorties possibles :
- `REJECT`
- `EXTEND`
- `PROBATION`
- `RECOMMEND_PROMOTION`

Règles principales :
- tous les critères de succès pré-enregistrés sont obligatoires ;
- DESIGN/VALIDATION ne sont jamais utilisés pour juger les seuils OOS de promotion ;
- métrique supportée mais indisponible => `EXTEND` ;
- métrique inconnue => `EXTEND`, sans estimation implicite ;
- critère mesuré en échec => `REJECT` ;
- budget candidat dépassé sur preuve OOS => `REJECT` ;
- critères OOS tous passés en SHADOW => `PROBATION` ;
- critères OOS tous passés en PROBATION => `RECOMMEND_PROMOTION` ;
- un candidat en `CANDIDATE` ne saute jamais directement vers PROBATION.

Le rapport est purement advisory : aucune transition lifecycle n'est appliquée,
aucune mutation AgentRegistry n'est effectuée et aucune autorité LIVE n'est créée.

## Tests

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
```

Puis :

```powershell
git status --short
```

Ne pas utiliser `git add -A`.
