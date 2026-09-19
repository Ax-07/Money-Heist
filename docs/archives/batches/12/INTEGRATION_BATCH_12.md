# Intégration — Batch 12 — Dashboard V1

## 1. Pré-requis

Le lot cible l'état Git suivant :

```text
8f6e3be28b2d987072897e5d90744f458cf40b4a
feat(shadow): complete Batch 11 shadow systems
```

Le dépôt doit être propre avant extraction afin d'identifier facilement les
changements du Batch 12.

## 2. Extraction

Extraire `money-heist_batch_12_dashboard-v1.zip` directement à la racine de :

```text
E:\0 money heist
```

Le ZIP contient les chemins `app/...`, `tests/...` et les fichiers de lot à la
racine. Il ne contient pas de dossier englobant supplémentaire.

## 3. Installation et tests

Dans PowerShell :

```powershell
cd "E:\0 money heist"
uv sync
uv run pytest -q
```

Résultat attendu si la baseline Batch 11 est intacte :

```text
312 passed
```

Les warnings Starlette/httpx déjà présents dans les batches précédents peuvent
rester visibles ; le Batch 12 n'ajoute aucune dépendance pour les contourner.

## 4. Lancer le Dashboard

```powershell
uv run uvicorn app.main:app --reload
```

Puis ouvrir :

```text
http://127.0.0.1:8000/dashboard
```

Au démarrage, si aucun run SHADOW n'a encore été observé dans le processus, les
valeurs opérationnelles sont affichées comme **Indisponible**. C'est volontaire.

## 5. Publier les résultats d'un runner SHADOW existant

Le Batch 12 ne modifie pas `ShadowFleetRunner`. Lorsqu'un composant applicatif
possède déjà le runner Batch 11, il peut l'envelopper avec l'observateur :

```python
from app.dashboard import DashboardShadowObserver, DashboardStore

store = DashboardStore()
app.state.dashboard_store = store
observed_shadow_runner = DashboardShadowObserver(shadow_runner, store)

fleet_result = await observed_shadow_runner.run(
    root_opportunity=root_opportunity,
    market_context=market_context,
    now=now,
)
```

`fleet_result` est exactement le résultat du runner métier. Une erreur de projection
Dashboard est journalisée mais ne remplace pas, n'annule pas et ne transforme pas le
résultat PAPER/SHADOW déjà produit.

Cette intégration est volontairement explicite : le Dashboard n'acquiert pas de
référence cachée vers le Risk Engine ou le broker et ne devient jamais un chemin
d'exécution.

## 6. Vérifications rapides

```powershell
# Toutes les routes Dashboard métier doivent être GET-only
uv run pytest -q tests/dashboard/test_api.py tests/dashboard/test_ui_contract.py

# Garde-fous PAPER/SHADOW et indisponibilité explicite
uv run pytest -q tests/dashboard/test_models.py tests/dashboard/test_store.py

# Projection Batch 09/10/11 + observateur non autoritaire
uv run pytest -q tests/dashboard/test_projection.py tests/dashboard/test_observer.py
```

## 7. Aucune configuration nouvelle

- aucune variable d'environnement ;
- aucune migration ;
- aucune dépendance ;
- aucun secret ;
- aucune clé exchange ;
- aucune configuration LIVE.
