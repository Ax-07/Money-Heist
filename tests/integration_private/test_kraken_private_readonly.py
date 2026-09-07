"""Opt-in private Kraken smoke test. It is read-only and never adds/cancels/modifies an order."""

import asyncio
import os

import pytest

from app.trading.live.auth import EnvironmentKrakenCredentialProvider
from app.trading.live.kraken_private import KrakenSpotPrivateRestClient

pytestmark = pytest.mark.skipif(
    os.getenv("MONEY_HEIST_RUN_KRAKEN_PRIVATE_TESTS") != "1",
    reason="Kraken private integration tests are explicit opt-in",
)


def test_private_credentials_can_authenticate_read_only():
    client = KrakenSpotPrivateRestClient(credentials=EnvironmentKrakenCredentialProvider())
    info = asyncio.run(client.get_api_key_info())
    assert isinstance(info.get("permissions", []), list)
