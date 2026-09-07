# Intégration — Batch 05 Risk Engine

1. Fermer le serveur de développement s'il tourne.
2. Extraire le contenu du ZIP à la racine du projet Money Heist.
3. Accepter la fusion des dossiers ; ce batch n'est censé remplacer aucun fichier existant.
4. Exécuter :

```powershell
uv sync
uv run pytest -q
```

## Résultat attendu

Les 62 tests déjà présents doivent rester verts et les nouveaux tests du Batch 05 doivent s'ajouter.

## Smoke import optionnel

```powershell
uv run python -c "from app.trading.risk import RiskEngine; print(RiskEngine)"
```

## Important avant LIVE

Ne pas utiliser `demo_profile()` comme profil LIVE. Les valeurs constitutionnelles Balanced restent à approuver explicitement avant l'activation réelle.
