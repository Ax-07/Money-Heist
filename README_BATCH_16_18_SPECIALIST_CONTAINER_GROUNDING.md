# Batch 16.18 — Specialist container grounding

## Constat LIVE_EVAL

La campagne `6d28b7c4-364f-4039-b59a-1dc34b941f08` termine 345/345 avec :

- 15 opportunités ;
- 3 `NO_ANALYSIS` ;
- 12 `MINI_CREW` ;
- 11 décisions finales `NO_TRADE` ;
- 0 erreur transport ;
- 0 `incomplete:max_output_tokens` ;
- 1 `UNGROUNDED_EVIDENCE` pendant `specialists_independent_round_1`.

Erreur :

`specialist evidence references unavailable input fields: opportunity.triggers`

## Cause

Le grounding des spécialistes utilisait `_leaf_paths()`, qui n'enregistrait que
les feuilles terminales. Un champ conteneur réellement présent, comme
`opportunity.triggers`, était donc rejeté même s'il faisait partie du payload
envoyé au spécialiste.

Le grounding final du Professor utilisait déjà la règle correcte : enregistrer
tous les chemins JSON réels, conteneurs compris.

## Correctif

- remplace `_leaf_paths()` par `_grounded_json_paths()` côté spécialistes ;
- chaque chemin réel non racine est autorisé, y compris dict/list conteneurs ;
- les chemins absents restent rejetés ;
- aucun alias supplémentaire n'est introduit ;
- aucune donnée fabriquée n'est autorisée.

## Invariants

- indépendance du premier round inchangée ;
- contamination guard inchangé ;
- prompts et modèles d'agents inchangés ;
- AI budget inchangé ;
- Risk Engine inchangé ;
- PaperBroker inchangé ;
- aucun trading LIVE.

## Validation

```powershell
uv run pytest -q tests/agents/test_specialists_v1.py
uv run pytest -q tests/agents/test_specialists_advanced.py
uv run pytest -q
```
