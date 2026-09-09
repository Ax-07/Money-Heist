# Batch 19b — Step 3 — Comparability, Provenance & OOS Gates

Baseline projet attendue avant Batch 19 : `96b2288`.

Ce step ajoute un gate d'evidence pour les campagnes de recrutement executees.
Il ne score pas les criteres de succes et ne recommande aucune promotion.

Garanties :
- baseline et candidat doivent rester strictement comparables sur dataset, role, periode, candles traitees et opportunites ;
- la configuration Backtest materielle doit etre identique hors metadata de recrutement ;
- le roster candidat doit ajouter exactement le candidat sans retirer d'incumbent ;
- les criteres de succes figes au planning ne peuvent pas deriver silencieusement ;
- DESIGN/VALIDATION peuvent servir au diagnostic mais jamais comme evidence de promotion ;
- l'evidence de promotion est fail-closed et exige OOS ;
- provenance explicite : run ids, business fingerprints, dataset, periode, rosters, campagne, execution et success criteria fingerprints ;
- evidence qualifiee explicitement `SIMULATED_HISTORICAL_REPLAY_PAPER` ;
- aucune mutation AgentRegistry, aucune transition lifecycle, aucun LIVE, aucune action de promotion.

Apres extraction a la racine :

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
git status --short
```

Ne pas committer avant validation locale complete. Ne pas utiliser `git add -A`.
