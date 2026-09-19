# Intégration — Batch 03

## 1. Pré-requis

- Batch 01 installé ;
- Batch 02 installé et validé ;
- `uv sync` fonctionnel ;
- les 26 tests existants passent avant copie du lot.

## 2. Copie

Extraire le ZIP à la racine du dépôt Money Heist.

Le ZIP ne remplace volontairement aucun fichier du Batch 01/02 : il ajoute uniquement les modules `features`, `scanner`, `replay` et leurs tests.

## 3. Dépendances

Aucune nouvelle dépendance Python n'est requise.

Exécuter tout de même :

```powershell
uv sync
```

## 4. Validation

```powershell
uv run pytest -q
```

Attendu pour le Batch 03 seul : 24 tests passent.

Attendu après intégration sur l'état annoncé du projet : 50 tests au total (26 existants + 24 nouveaux), sous réserve qu'aucun test local supplémentaire n'ait été ajouté entre-temps.

## 5. Exemple minimal

```python
from app.market.features import FeatureEngine
from app.market.scanner import DeterministicScanner

features = FeatureEngine().compute(
    candles,
    symbol="BTCUSDT",
    timeframe="5m",
    source_snapshot_id="<id-du-snapshot-batch-02>",
)

result = DeterministicScanner().scan(
    features,
    system_id="balanced_v1",
)

if result.opportunity is not None:
    print(result.opportunity.model_dump())
```

## 6. Notes d'architecture

- `CandidateOpportunity` ne contient pas de direction de trade.
- Le scanner n'est pas le futur AI Compute Gate ; il ne fait que produire une priorité et des raisons.
- `replay_scanner()` sert à vérifier la reproductibilité et le non-look-ahead. Ce n'est pas encore le moteur de backtest de la couche Evaluation.
- Les seuils du scanner sont configurables dans `ScannerConfig` sans être des paramètres de risque constitutionnels.
