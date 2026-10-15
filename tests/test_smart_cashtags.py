from app.runtime.symbols import normalize_smart_cashtags


def test_known_native_coin_becomes_its_cashtag():
    text = "Bitcoin got the call.\n\n@LSDinmycoffee's bitcoin:native long."

    assert normalize_smart_cashtags(text) == (
        "Bitcoin got the call.\n\n@LSDinmycoffee's $BTC long."
    )


def test_unknown_slug_takes_the_tweets_one_unwritten_ticker():
    text = "$ETH and fartcoin:native both ripping"

    assert (
        normalize_smart_cashtags(text, ["ETH", "FART"]) == "$ETH and $FART both ripping"
    )


def test_unknown_slug_without_a_ticker_is_uppercased():
    assert normalize_smart_cashtags("zcash:native", []) == "$ZCASH"


def test_text_without_smart_cashtags_is_unchanged():
    assert normalize_smart_cashtags("$AAPL 200C", ["AAPL"]) == "$AAPL 200C"
    assert normalize_smart_cashtags(None) is None
