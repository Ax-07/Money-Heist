# Money Heist — Batch 18a Step 4

## Fermeture du sous-batch : API publique, exports et documentation

Ce Step 4 ne change pas la logique de réputation/ablation validée aux Steps 1–3. Il ferme le
sous-batch 18a en consolidant les imports publics de `app.evaluation`, en ajoutant une sérialisation
JSON dédiée aux rapports advisory et en fournissant une mise à jour documentaire idempotente qui
préserve les modifications locales existantes.

### Installation

Extraire le ZIP à la racine du dépôt après les Steps 1, 2 et 3.

Puis appliquer les addenda documentaires :

```powershell
uv run python apply_batch_18a_step4_docs.py
```

Le script met à jour les copies racine et/ou `docs/` présentes de :
- `06_EVALUATION_ET_APPRENTISSAGE.md` ;
- `08_API_ET_MODELES_DE_DONNEES.md` ;
- `09_ROADMAP_DEVELOPPEMENT.md`.

Les blocs sont balisés et idempotents ; le contenu local déjà présent est conservé.

### Validation ciblée

```powershell
uv run pytest -q tests/evaluation/test_reputation_exports.py tests/evaluation/test_batch18a_docs_updater.py tests/evaluation/test_reputation_public_api.py
```

### Validation complète

```powershell
uv run pytest -q
```

### Frontières conservées

- aucun seuil de production inventé ;
- aucune mutation automatique de `AgentRegistry` ;
- `auto_apply=False` ;
- aucune capacité Broker, Risk ou LIVE ;
- aucune requalification DESIGN/VALIDATION en OOS.
