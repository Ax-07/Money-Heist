import asyncio
import json
import socket

import pytest

from app.trading.live.auth import KrakenCredentials, KrakenNonce
from app.trading.live.errors import LiveAmbiguousSubmissionError
from app.trading.live.kraken_private import KrakenPrivateClientConfig, KrakenSpotPrivateRestClient


class Credentials:
    def load(self):
        return KrakenCredentials("fake-public", "c2VjcmV0")


class Sender:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        result = self.outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def ok(result):
    return 200, json.dumps({"error": [], "result": result}).encode()


def test_private_read_retries_bounded_transport_failure():
    sender = Sender([socket.timeout(), ok({"open": {}})])
    client = KrakenSpotPrivateRestClient(
        credentials=Credentials(), nonce=KrakenNonce(clock_ns=lambda: 2_000_000_000), sender=sender,
        config=KrakenPrivateClientConfig(read_max_attempts=2, backoff_seconds=0),
    )
    assert asyncio.run(client.get_open_orders(client_order_id="abc")) == {"open": {}}
    assert len(sender.calls) == 2


def test_add_order_is_never_retried_after_timeout():
    sender = Sender([socket.timeout(), ok({"txid": ["SHOULD-NOT-BE-USED"]})])
    client = KrakenSpotPrivateRestClient(
        credentials=Credentials(), sender=sender,
        config=KrakenPrivateClientConfig(read_max_attempts=3, backoff_seconds=0),
    )
    with pytest.raises(LiveAmbiguousSubmissionError):
        asyncio.run(client.add_order({"pair": "XBTEUR", "type": "buy", "ordertype": "market", "volume": "0.01", "cl_ord_id": "abc"}))
    assert len(sender.calls) == 1


def test_cancel_is_never_retried_after_timeout():
    sender = Sender([socket.timeout(), ok({"count": 1})])
    client = KrakenSpotPrivateRestClient(credentials=Credentials(), sender=sender)
    with pytest.raises(LiveAmbiguousSubmissionError):
        asyncio.run(client.cancel_order(client_order_id="abc"))
    assert len(sender.calls) == 1


def test_private_client_exposes_no_arbitrary_request_method():
    assert not hasattr(KrakenSpotPrivateRestClient, "request")
    assert not hasattr(KrakenSpotPrivateRestClient, "post")
    assert not hasattr(KrakenSpotPrivateRestClient, "withdraw")
