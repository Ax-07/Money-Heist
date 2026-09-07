from __future__ import annotations


class ReadOnlyKrakenPrivateView:
    """Capability wrapper for preflight/reconciliation.

    It deliberately exposes no AddOrder/CancelOrder member, so the Batch 15
    operator preflight cannot perform an exchange write even if called wrongly.
    """

    def __init__(self, client) -> None:
        self._client = client

    async def get_api_key_info(self):
        return await self._client.get_api_key_info()

    async def get_balance(self):
        return await self._client.get_balance()

    async def get_open_orders(self, *, client_order_id: str | None = None):
        return await self._client.get_open_orders(client_order_id=client_order_id)

    async def get_closed_orders(self, *, client_order_id: str | None = None):
        return await self._client.get_closed_orders(client_order_id=client_order_id)

    async def get_trades_history(self):
        return await self._client.get_trades_history()
