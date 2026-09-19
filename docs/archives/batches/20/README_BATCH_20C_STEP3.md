# Batch 20c — Step 3 — Aggregation & optional Red Team

## Objectif

Fermer la phase d'exécution Task Force avec un rapport advisory déterministe, auditable et
sans autorité de trading.

## Flux

`TaskForceMultiMemberExecution(COMPLETED)`
→ validation des fingerprints Request / Plan / ExecutionContract
→ validation stricte de l'ordre et de l'identité des membres
→ agrégation provenance-preserving
→ extraction séparée des contributions `red_team`
→ `TaskForceReport`

## Choix de conception

L'agrégation ne lance aucun nouvel appel IA. Une contribution Red Team doit déjà appartenir
à la composition approuvée et avoir été exécutée au Step 2. Si `red_team_required=True` et
qu'aucun membre `red_team` n'est présent dans l'exécution terminée, l'agrégation échoue.

Le rapport ne calcule volontairement ni vote sémantique, ni score de consensus, ni moyenne
de confiance. Les réponses, findings, incertitudes et questions de suivi restent rattachés à
leurs membres d'origine.

La contribution Task Force de Palermo ne remplace pas le `PalermoReview` du pipeline principal.
L'orchestration existante conserve son propre Red Team contract.

## Sécurité

Le rapport reste explicitement :

- `advisory_only=True` ;
- `trade_proposal_authority=False` ;
- `registry_mutation=False` ;
- `risk_authority=False` ;
- `live_authority=False`.

Une exécution `BLOCKED` ou `FAILED`, une comptabilité incomplète, un fingerprint stale, un
ordre de membres modifié ou une Task Force expirée est refusé fail-closed.

## Validation

```powershell
uv run pytest -q tests/task_force/test_task_force_aggregation.py
uv run pytest -q
```
