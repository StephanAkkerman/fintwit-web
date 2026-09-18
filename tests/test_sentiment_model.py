import re

import pytest

from app.ml.sentiment import (
    FinTwitSentiment,
    attribute_segments,
    label_from_score,
    signed_score,
    split_main_and_quoted_text,
    split_segments,
)


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


class _StubPipeline:
    """Stands in for the FinTwitBERT pipeline with keyword rules.

    Lets the segmentation and attribution logic be exercised without loading
    half a gigabyte of BERT (or reaching the network) in the test suite.
    """

    BULL = re.compile(r"\b(long|moon|print\w*|rip|calls|buy\w*|up)\b", re.I)
    BEAR = re.compile(r"\b(short|puts|dead|dump\w*|crash\w*|sell\w*|down)\b", re.I)

    def __init__(self):
        self.batches: list[list[str]] = []

    def __call__(self, texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        self.batches.append(list(texts))
        out = []
        for text in texts:
            if self.BEAR.search(text):
                out.append({"label": "BEARISH", "score": 0.88})
            elif self.BULL.search(text):
                out.append({"label": "BULLISH", "score": 0.91})
            else:
                out.append({"label": "NEUTRAL", "score": 0.70})
        return out


def _model() -> FinTwitSentiment:
    model = FinTwitSentiment()
    model._pipeline = _StubPipeline()
    return model


class TestSignedScores:
    """Every consumer reads the sign: `score > 0.1` is bullish, `< -0.1` bearish."""

    @pytest.mark.parametrize(
        ("label", "confidence", "expected"),
        [("BULLISH", 0.9, 0.9), ("BEARISH", 0.9, -0.9), ("NEUTRAL", 0.9, 0.0)],
    )
    def test_signed_score(self, label, confidence, expected):
        assert signed_score(label, confidence) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("score", "expected"),
        [(0.9, "BULLISH"), (-0.9, "BEARISH"), (0.05, "NEUTRAL"), (0.0, "NEUTRAL")],
    )
    def test_label_from_score(self, score, expected):
        assert label_from_score(score) == expected

    @pytest.mark.asyncio
    async def test_bearish_text_scores_negative(self):
        verdict = await _model().classify("$INTC is dead money, buying puts")
        assert verdict["label"] == "BEARISH"
        assert verdict["score"] < 0

    @pytest.mark.asyncio
    async def test_bullish_text_scores_positive(self):
        verdict = await _model().classify("$NVDA is printing money")
        assert verdict["label"] == "BULLISH"
        assert verdict["score"] > 0


class TestSegmentation:
    def test_short_text_is_one_segment(self):
        assert split_segments("$NVDA to the moon") == ["$NVDA to the moon"]

    def test_sentences_and_newlines_split(self):
        segments = split_segments(
            "First claim here. Second claim here.\nAnd a third claim"
        )
        assert segments == [
            "First claim here.",
            "Second claim here.",
            "And a third claim",
        ]

    def test_fragments_are_dropped(self):
        assert split_segments("Edit: typo. This sentence is long enough.") == [
            "This sentence is long enough."
        ]

    def test_empty_text(self):
        assert split_segments("") == []
        assert split_segments("   ") == []

    @pytest.mark.asyncio
    async def test_long_post_is_not_judged_on_its_opening(self):
        # One truncated read would return the first claim's label for the
        # whole post; the mean of the segments reflects all of it.
        model = _model()
        verdict = await model.classify(
            "$NVDA is printing money right now.\n"
            "The datacenter backlog keeps growing.\n"
            "But margins are crashing and I am buying puts."
        )
        assert len(model._pipeline.batches[0]) == 3
        assert verdict["label"] == "NEUTRAL"  # two bullish, one strongly bearish


class TestPerTickerAttribution:
    TEXT = (
        "$NVDA vs $INTC: the only pair trade that matters.\n"
        "I am long $NVDA, the datacenter business is printing.\n"
        "$INTC is dead money and I am buying puts."
    )

    @pytest.mark.asyncio
    async def test_opposing_calls_get_opposite_signs(self):
        parts = await _model().classify_parts(self.TEXT, ["NVDA", "INTC"])
        per_ticker = parts["tickers"]
        assert per_ticker["NVDA"] > 0
        assert per_ticker["INTC"] < 0

    @pytest.mark.asyncio
    async def test_a_segment_naming_both_is_skipped_when_better_exists(self):
        # The opening line names both, so it says nothing about either in
        # particular; each is scored from the line that names only it.
        parts = await _model().classify_parts(self.TEXT, ["NVDA", "INTC"])
        assert parts["tickers"]["NVDA"] == pytest.approx(0.91)
        assert parts["tickers"]["INTC"] == pytest.approx(-0.88)

    @pytest.mark.asyncio
    async def test_shared_segment_is_used_when_nothing_else_names_the_ticker(self):
        parts = await _model().classify_parts(
            "Long $NVDA and $AMD here", ["NVDA", "AMD"]
        )
        # Both fall back to the one shared line, which agrees with the post.
        assert parts["tickers"] == {}

    @pytest.mark.asyncio
    async def test_ticker_matching_the_post_score_is_not_stored(self):
        parts = await _model().classify_parts("$NVDA is printing money", ["NVDA"])
        assert parts["tickers"] == {}
        assert parts["main"]["score"] > 0

    @pytest.mark.asyncio
    async def test_no_tickers_means_no_attribution(self):
        parts = await _model().classify_parts(self.TEXT)
        assert parts["tickers"] == {}

    @pytest.mark.asyncio
    async def test_quoted_text_never_attributes(self):
        # A quoted tweet is someone else's opinion, not a call by this author.
        model = _model()
        parts = await model.classify_parts(
            "$NVDA is printing money\n\n> [@other](https://x.com/o):\n"
            "> $INTC is dead money and I am buying puts",
            ["NVDA", "INTC"],
        )
        assert parts["main"]["score"] > 0
        assert parts["quoted"]["score"] < 0
        assert "INTC" not in parts["tickers"]

    def test_short_symbols_are_matched_case_sensitively(self):
        # "on" the preposition is not $ON the ticker.
        assert attribute_segments(["I am on the fence about this"], ["ON"]) == {}
        assert attribute_segments(["Buying ON here at these levels"], ["ON"]) == {
            "ON": [0]
        }

    def test_longer_symbols_match_case_insensitively(self):
        assert attribute_segments(["nvda is printing money"], ["NVDA"]) == {"NVDA": [0]}

    def test_cashtags_and_hashtags_both_match(self):
        assert attribute_segments(["$NVDA is printing"], ["NVDA"]) == {"NVDA": [0]}
        assert attribute_segments(["#NVDA is printing"], ["NVDA"]) == {"NVDA": [0]}
