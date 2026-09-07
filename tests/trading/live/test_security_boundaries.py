from app.trading.live.activation import DenyAllLiveAuthorization
from app.trading.live.broker import KrakenSpotLiveBroker
from app.trading.live.kraken_private import KrakenSpotPrivateRestClient


def test_no_withdrawal_capability_exists_on_live_boundaries():
    for cls in (KrakenSpotLiveBroker, KrakenSpotPrivateRestClient):
        names = {name.lower() for name in dir(cls)}
        assert not any("withdraw" in name for name in names)
        assert not any("transfer" in name for name in names)


def test_batch14_has_no_environment_live_enable_switch():
    assert DenyAllLiveAuthorization().get_authorization(system_id="balanced_v1").authorized is False
