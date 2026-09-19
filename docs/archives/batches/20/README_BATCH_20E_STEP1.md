# Batch 20e — Step 1 — Task Force Evaluation & Economic Cost

Ce Step ajoute une couche d'évaluation read-only pour les Task Forces.

## Principes

- Les métriques opérationnelles viennent uniquement de `TaskForceMultiMemberExecution` et
  `TaskForceReport` déjà scellés.
- Aucun score global de réputation ou de promotion n'est créé.
- Le coût réel, les attempts, la latence, la taille de l'équipe et la présence Red Team sont
  mesurés séparément.
- Les métriques marginales (`trading_net`, `economic_net`, drawdown) restent `UNAVAILABLE`
  tant qu'aucune paire baseline/treatment strictement comparable n'est fournie.
- Une comparaison doit conserver dataset, rôle, période, nombre d'opportunités, statut OOS et
  fingerprint de comparaison identiques. La baseline exclut la Task Force ; le treatment lie
  exactement le fingerprint du `TaskForceReport` évalué.
- L'évaluation reste advisory-only : aucune mutation registry, aucune autorité Risk/LIVE,
  aucune création de `TradeProposal`.

## Fichier ajouté

- `app/evaluation/task_force.py`

## Test ciblé

```powershell
uv run pytest -q tests/evaluation/test_task_force_evaluation.py
```
