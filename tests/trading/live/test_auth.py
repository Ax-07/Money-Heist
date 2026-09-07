from app.trading.live.auth import KrakenCredentials, KrakenNonce, sign_kraken_request


def test_official_kraken_signature_vector():
    secret = "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3pd5nE9qa99HAZtuZuj6F1huXg=="
    payload = {
        "nonce": "1616492376594",
        "ordertype": "limit",
        "pair": "XBTUSD",
        "price": 37500,
        "type": "buy",
        "volume": 1.25,
    }
    assert sign_kraken_request(url_path="/0/private/AddOrder", payload=payload, api_secret=secret) == (
        "4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+UClSV5n9E6aSS8MPtnRfp32bAb0nmbRn6H8ndwLUQ=="
    )


def test_credentials_repr_redacts_both_values():
    value = repr(KrakenCredentials("public-key", "c2VjcmV0"))
    assert "public-key" not in value
    assert "c2VjcmV0" not in value
    assert "redacted" in value


def test_nonce_strictly_increases_even_when_clock_does_not():
    nonce = KrakenNonce(clock_ns=lambda: 1_000_000_000)
    assert [nonce.next(), nonce.next(), nonce.next()] == [1000, 1001, 1002]
