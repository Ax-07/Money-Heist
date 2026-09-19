# Intégration — Batch 14 LIVE Broker sécurisé

## Installation

Extraire le ZIP directement à la racine du dépôt `E:\0 money heist` en conservant l'arborescence.

Puis :

```powershell
cd "E:\0 money heist"
uv sync
uv run pytest -q
```

Aucune nouvelle dépendance importante n'est ajoutée.

## Ce que le lot ajoute

- `app/trading/live/` : modèles, port `LiveBroker`, auth Kraken, client privé allowlisté, broker Spot, garde d'autorisation, audit/store testables ;
- tests unitaires hors réseau ;
- test privé read-only explicitement opt-in ;
- décision Spot vs dérivés ;
- documentation sécurité ;
- noms de variables Kraken vides dans `.env.example`.

## Important : LIVE reste désactivé

Le code de composition existant n'est pas modifié pour router vers le broker LIVE. `Settings` continue de refuser `runtime_mode=LIVE` et `DenyAllLiveAuthorization` refuse toute soumission.

Les variables d'environnement Kraken chargent uniquement des credentials ; elles n'autorisent jamais l'exécution.

## Tests privés opt-in

Ne les exécuter qu'avec une clé de test dédiée sans retrait et seulement si vous souhaitez vérifier l'authentification read-only :

```powershell
$env:MONEY_HEIST_RUN_KRAKEN_PRIVATE_TESTS="1"
uv run pytest -q tests/integration_private
```

Ce test n'ajoute, ne modifie et n'annule aucun ordre.

## Non inclus

- activation LIVE ;
- configuration des 100 € ;
- changement du Risk Engine ;
- changement des profils de risque ;
- Dashboard d'exécution ;
- WebSocket ;
- dérivés ;
- retraits/transferts ;
- Rio/Denver/Recruitment Engine.

## Compatibilité avec la suite historique

Le lot inclut `tests/trading/live/__init__.py` afin que Pytest ne confonde pas le test LIVE `test_security_boundaries.py` avec les fichiers historiques portant le même basename dans d'autres répertoires.

Les tests asynchrones Batch 14 sont exécutés avec `asyncio.run(...)` : aucune installation de `pytest-asyncio` n'est nécessaire.

Si une version antérieure du ZIP Batch 14 a déjà été extraite, ré-extraire ce ZIP corrigé à la racine en autorisant le remplacement des fichiers suffit.
