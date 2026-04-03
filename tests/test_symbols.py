from app.runtime.symbols import extract_symbols_from_text, merge_symbols


def test_extract_symbols_from_text_parses_tickers_and_hashtags():
    tickers, hashtags = extract_symbols_from_text(
        "Bullish on $aapl and #btc while watching #macro"
    )
    assert tickers == ["AAPL"]
    assert hashtags == ["BTC", "MACRO"]


def test_merge_symbols_combines_existing_with_text_symbols_without_duplicates():
    tickers, hashtags = merge_symbols(
        "Setup on $SPY and #btc",
        ["AAPL", "$SPY"],
        ["macro", "#BTC"],
    )
    assert tickers == ["AAPL", "SPY"]
    assert hashtags == ["MACRO", "BTC"]


def test_merge_symbols_handles_empty_text_and_none_arrays():
    tickers, hashtags = merge_symbols(None, None, None)
    assert tickers == []
    assert hashtags == []
