from app.runtime.options_intent import classify_options_intent


def test_classify_options_intent_detects_compact_call_contract():
    result = classify_options_intent("$TSLA AUG 390c up about 15%")

    assert result["is_options_tweet"] is True
    context = result["options_context"]
    assert context["classification"] == "OPTIONS"
    assert context["side"] == "CALL"
    assert context["contract_count"] >= 1

    tsla_contract = next(c for c in context["contracts"] if c["symbol"] == "TSLA")
    assert tsla_contract["right"] == "CALL"
    assert tsla_contract["strike"] == 390.0
    assert tsla_contract["expiry"] == "AUG"


def test_classify_options_intent_detects_flow_call_buyer_pattern():
    result = classify_options_intent("$STM - $549K Call buyer")

    assert result["is_options_tweet"] is True
    context = result["options_context"]
    assert context["side"] == "CALL"

    stm_contract = next(c for c in context["contracts"] if c["symbol"] == "STM")
    assert stm_contract["right"] == "CALL"
    assert stm_contract["notional_usd"] == 549000.0


def test_classify_options_intent_detects_mixed_side_multiline_flow():
    text = "\n".join(
        [
            "$NVDA AUG 140c (8/16) OI confirmed",
            "$NVDA AUG 120p (8/16) scale in",
            "$STM - $549K Call buyer",
        ]
    )

    result = classify_options_intent(text)

    assert result["is_options_tweet"] is True
    context = result["options_context"]
    assert context["side"] == "MIXED"
    assert "open_interest" in context["keyword_hits"]


def test_classify_options_intent_ignores_plain_equity_chatter():
    result = classify_options_intent(
        "$AAPL broke resistance at 190. Added shares for a spot swing trade."
    )

    assert result["is_options_tweet"] is False
    assert result["options_context"]["classification"] == "SPOT_OR_OTHER"
