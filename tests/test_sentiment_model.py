from app.ml.sentiment import split_main_and_quoted_text


def test_split_main_and_quoted_text_for_quote_tweet():
    text = (
        "Bullish update from me\n\n> [@user](https://x.com/user):\n> Bearish prior idea"
    )

    main, quoted = split_main_and_quoted_text(text)

    assert main == "Bullish update from me"
    assert quoted is not None
    assert "Bearish prior idea" in quoted


def test_split_main_and_quoted_text_without_quote_block():
    text = "Just a standalone tweet"

    main, quoted = split_main_and_quoted_text(text)

    assert main == text
    assert quoted is None
