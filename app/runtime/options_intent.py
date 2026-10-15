import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MONTH_PATTERN = (
    r"JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|"
    r"JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:T(?:EMBER)?)?|"
    r"OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?"
)

_CASHTAG_RE = re.compile(r"\$([A-Z][A-Z0-9]{0,9})")

_COMPACT_CONTRACT_RE = re.compile(
    rf"""
    (?P<symbol>\$[A-Z][A-Z0-9]{{0,9}})
    (?:\s+(?P<month>{_MONTH_PATTERN}))?
    \s+(?P<strike>\d{{1,5}}(?:\.\d{{1,2}})?)
    \s*(?P<right>[cCpP])\b
    (?:\s*\((?P<expiry>\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?)\))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_EXPLICIT_CONTRACT_RE = re.compile(
    rf"""
    (?P<symbol>\$[A-Z][A-Z0-9]{{0,9}})
    (?:\s+(?P<month>{_MONTH_PATTERN}))?
    \s+(?P<strike>\d{{1,5}}(?:\.\d{{1,2}})?)
    \s*(?P<right>calls?|puts?)\b
    (?:\s*\((?P<expiry>\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?)\))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_FLOW_RE = re.compile(
    r"""
    (?P<symbol>\$[A-Z][A-Z0-9]{0,9})
    [^\n]{0,80}?
    \$(?P<notional>\d+(?:\.\d+)?)\s*(?P<mult>[KMB])
    \s*(?P<right>calls?|puts?)\b
    (?:\s+(?P<tag>buyer|seller|sweep|block))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SYMBOL_RIGHT_RE = re.compile(
    r"(?P<symbol>\$[A-Z][A-Z0-9]{0,9})[^\n]{0,48}?\b(?P<right>calls?|puts?)\b",
    re.IGNORECASE,
)

_DATE_EXPIRY_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")

_KEYWORD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("flow", re.compile(r"\bflow\b", re.IGNORECASE)),
    ("open_interest", re.compile(r"\b(?:oi|open\s+interest)\b", re.IGNORECASE)),
    ("sweep", re.compile(r"\bsweep(?:s)?\b", re.IGNORECASE)),
    ("block", re.compile(r"\bblock(?:s)?\b", re.IGNORECASE)),
    ("premium", re.compile(r"\bpremium\b", re.IGNORECASE)),
    ("expiry", re.compile(r"\b(?:exp|expiry|dte)\b", re.IGNORECASE)),
    ("contracts", re.compile(r"\bcontract(?:s)?\b", re.IGNORECASE)),
    ("straddle", re.compile(r"\bstraddle\b", re.IGNORECASE)),
    ("strangle", re.compile(r"\bstrangle\b", re.IGNORECASE)),
]


def _normalize_right(value: str | None) -> str | None:
    if not value:
        return None

    token = value.strip().upper()
    if token.startswith("C"):
        return "CALL"
    if token.startswith("P"):
        return "PUT"
    return None


def _normalize_expiry(month: str | None, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if month:
        return month[:3].upper()
    return None


def _notional_to_usd(value: str | None, multiplier: str | None) -> float | None:
    if not value or not multiplier:
        return None

    scales = {"K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}
    scale = scales.get(multiplier.upper())
    if scale is None:
        return None

    return float(value) * scale


def _keyword_hits(text: str) -> list[str]:
    hits: list[str] = []
    for label, pattern in _KEYWORD_PATTERNS:
        if pattern.search(text):
            hits.append(label)
    return hits


def _side_from_counts(call_count: int, put_count: int, text: str) -> str:
    if call_count > 0 and put_count > 0:
        return "MIXED"
    if call_count > 0:
        return "CALL"
    if put_count > 0:
        return "PUT"

    has_call_word = re.search(r"\bcall(?:s)?\b", text, flags=re.IGNORECASE) is not None
    has_put_word = re.search(r"\bput(?:s)?\b", text, flags=re.IGNORECASE) is not None
    if has_call_word and has_put_word:
        return "MIXED"
    if has_call_word:
        return "CALL"
    if has_put_word:
        return "PUT"
    return "UNKNOWN"


def _confidence(score: int) -> str:
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def classify_options_intent(text: str | None) -> dict[str, Any]:
    content = (text or "").strip()
    if not content:
        return {
            "is_options_tweet": False,
            "options_context": {
                "classification": "SPOT_OR_OTHER",
                "score": 0,
                "confidence": "low",
                "side": "UNKNOWN",
                "contract_count": 0,
                "contracts": [],
                "keyword_hits": [],
                "cashtags": [],
            },
        }

    contracts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float | None, str | None, float | None]] = set()

    def add_contract(
        symbol: str,
        right: str,
        strike: float | None,
        expiry: str | None,
        notional_usd: float | None,
        source: str,
    ) -> None:
        key = (symbol, right, strike, expiry, notional_usd)
        if key in seen:
            return
        seen.add(key)
        contracts.append(
            {
                "symbol": symbol,
                "right": right,
                "strike": strike,
                "expiry": expiry,
                "notional_usd": notional_usd,
                "source": source,
            }
        )

    for match in _COMPACT_CONTRACT_RE.finditer(content):
        right = _normalize_right(match.group("right"))
        if right is None:
            continue
        add_contract(
            symbol=match.group("symbol")[1:].upper(),
            right=right,
            strike=float(match.group("strike")),
            expiry=_normalize_expiry(match.group("month"), match.group("expiry")),
            notional_usd=None,
            source="compact",
        )

    for match in _EXPLICIT_CONTRACT_RE.finditer(content):
        right = _normalize_right(match.group("right"))
        if right is None:
            continue
        add_contract(
            symbol=match.group("symbol")[1:].upper(),
            right=right,
            strike=float(match.group("strike")),
            expiry=_normalize_expiry(match.group("month"), match.group("expiry")),
            notional_usd=None,
            source="explicit",
        )

    for match in _FLOW_RE.finditer(content):
        right = _normalize_right(match.group("right"))
        if right is None:
            continue
        add_contract(
            symbol=match.group("symbol")[1:].upper(),
            right=right,
            strike=None,
            expiry=None,
            notional_usd=_notional_to_usd(match.group("notional"), match.group("mult")),
            source="flow",
        )

    for match in _SYMBOL_RIGHT_RE.finditer(content):
        right = _normalize_right(match.group("right"))
        if right is None:
            continue
        add_contract(
            symbol=match.group("symbol")[1:].upper(),
            right=right,
            strike=None,
            expiry=None,
            notional_usd=None,
            source="symbol_right",
        )

    keyword_hits = _keyword_hits(content)
    cashtags = sorted({m.group(1).upper() for m in _CASHTAG_RE.finditer(content)})

    has_strike = any(c["strike"] is not None for c in contracts)
    has_right = any(c["right"] in {"CALL", "PUT"} for c in contracts)
    has_expiry = _DATE_EXPIRY_RE.search(content) is not None or any(
        c["expiry"] for c in contracts
    )
    has_notional = any(c["notional_usd"] is not None for c in contracts)

    score = 0
    if contracts:
        score += 2
    if has_strike:
        score += 2
    if has_right:
        score += 1
    score += min(len(keyword_hits), 3)
    if has_expiry:
        score += 1
    if has_notional:
        score += 1

    is_options = (score >= 4 and has_right) or (has_strike and has_right)

    call_count = sum(1 for c in contracts if c["right"] == "CALL")
    put_count = sum(1 for c in contracts if c["right"] == "PUT")

    context = {
        "classification": "OPTIONS" if is_options else "SPOT_OR_OTHER",
        "score": score,
        "confidence": _confidence(score),
        "side": _side_from_counts(call_count, put_count, content),
        "contract_count": len(contracts),
        "contracts": contracts,
        "keyword_hits": keyword_hits,
        "cashtags": cashtags,
    }

    return {
        "is_options_tweet": is_options,
        "options_context": context,
    }


_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
_ANY_CASE_CASHTAG_RE = re.compile(r"\$([A-Z][A-Z0-9]{0,9})\b", re.IGNORECASE)


def is_specific_contract(contract: dict[str, Any], tickers: set[str]) -> bool:
    """Whether *contract* names a real underlying and a detail of the trade.

    A call/put alone is not enough (issue #216): "Bitcoin got the call" or a
    betting slip priced "at $0.49" are not options trades. The contract needs a
    ticker-shaped symbol, a strike, expiry, premium or price, and the symbol
    must be one the tweet tags as a ticker, unless a strike makes the contract
    unambiguous anyway ("SPY 590P" is written without a cashtag).
    """
    symbol = str(contract.get("symbol") or "").upper()
    if not _SYMBOL_RE.match(symbol):
        return False
    if contract.get("right") not in {"CALL", "PUT"}:
        return False
    has_strike = contract.get("strike") is not None
    has_detail = has_strike or any(
        contract.get(key) is not None for key in ("expiry", "notional_usd", "price")
    )
    return has_detail and (symbol in tickers or has_strike)


def _not_options(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_options_tweet": False,
        "options_context": {
            **context,
            "classification": "SPOT_OR_OTHER",
            "side": "UNKNOWN",
            "contract_count": 0,
            "contracts": [],
        },
    }


def refine_options_result(result: dict[str, Any], tickers: set[str]) -> dict[str, Any]:
    """Keep only specific contracts; no specific contract means not options."""
    if not result.get("is_options_tweet"):
        return result

    context = dict(result.get("options_context") or {})
    contracts = [
        c for c in context.get("contracts") or [] if is_specific_contract(c, tickers)
    ]
    if not contracts:
        return _not_options(context)

    rights = {c["right"] for c in contracts}
    context.update(
        contracts=contracts,
        contract_count=len(contracts),
        side=rights.pop() if len(rights) == 1 else "MIXED",
    )
    return {"is_options_tweet": True, "options_context": context}


async def detect_options(
    text: str | None,
    quoted_text: str | None = None,
    recognizer: Any = None,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Classify a tweet as options or not, preferring the NER model.

    *recognizer* is an :class:`app.ml.options_ner.OptionsRecognizer`. Without
    one, or when it fails, the regex heuristic above decides instead. Either
    way a tweet that quotes an options tweet counts as one (issue #64).

    *tickers* are the symbols the tweet is tagged with; cashtags in either
    text are added to them. Only contracts that pass
    :func:`is_specific_contract` make a tweet an options tweet.
    """
    known = {t.strip().lstrip("$").upper() for t in tickers or [] if t}
    for part in (text, quoted_text):
        known |= {m.group(1).upper() for m in _ANY_CASE_CASHTAG_RE.finditer(part or "")}

    if recognizer is not None:
        try:
            result = await recognizer.recognize(text, quoted_text)
            return refine_options_result(result, known)
        except Exception as exc:
            logger.warning("[options] recognizer failed, using heuristic: %r", exc)

    result = refine_options_result(classify_options_intent(text), known)
    if not result["is_options_tweet"] and quoted_text:
        quoted = refine_options_result(classify_options_intent(quoted_text), known)
        if quoted["is_options_tweet"]:
            return quoted
    return result
