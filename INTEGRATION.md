# Intégration — Batch 04 Paper Broker

Ce lot est volontairement additif : il n’écrase aucun fichier des Batchs 01 à 03 hors de nouveaux chemins sous `app/trading/paper/` et `tests/trading/`.

## Installation

Depuis la racine du projet :

```powershell
uv sync
uv run pytest -q
```

Aucune nouvelle dépendance n’est ajoutée.

## Contrôle rapide manuel

```python
import asyncio
from decimal import Decimal

from app.trading.paper import (
    OrderSide,
    OrderType,
    PaperBroker,
    PaperOrderRequest,
)


async def main() -> None:
    broker = PaperBroker()
    await broker.process_price("BTCUSDT", Decimal("50000"))
    await broker.submit_order(
        PaperOrderRequest(
            system_id="balanced_v1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.001"),
            client_order_id="demo-001",
        )
    )
    print(await broker.get_account_state())


asyncio.run(main())
```

## Note de compatibilité

Le projet réel des Batchs 01–03 n’était pas présent dans les sources de cette conversation. Le lot évite donc volontairement de modifier `pyproject.toml`, les modèles déjà existants ou les modules des Batchs précédents. Si vos Batchs 01–03 exposent déjà un contrat `Broker` ou des modèles `OrderIntent/BrokerOrder`, le prochain petit raccord pourra adapter ce module sans changer son moteur comptable.
