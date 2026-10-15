import re
from typing import Iterable

_TICKER_RE = re.compile(r"(?<!\w)\$([A-Za-z][A-Za-z0-9]{0,9})\b")
_HASHTAG_RE = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_]{0,29})\b")


def _normalize(values: Iterable[str] | None, *, upper: bool) -> list[str]:
    if not values:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        token = value.strip().lstrip("#$")
        if not token:
            continue
        token = token.upper() if upper else token
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def extract_symbols_from_text(text: str | None) -> tuple[list[str], list[str]]:
    if not text:
        return [], []

    tickers = _normalize(_TICKER_RE.findall(text), upper=True)
    hashtags = _normalize(_HASHTAG_RE.findall(text), upper=True)
    return tickers, hashtags


def merge_symbols(
    text: str | None,
    tickers: Iterable[str] | None,
    hashtags: Iterable[str] | None,
) -> tuple[list[str], list[str]]:
    base_tickers = _normalize(tickers, upper=True)
    base_hashtags = _normalize(hashtags, upper=True)
    text_tickers, text_hashtags = extract_symbols_from_text(text)

    merged_tickers = _normalize([*base_tickers, *text_tickers], upper=True)
    merged_hashtags = _normalize([*base_hashtags, *text_hashtags], upper=True)
    return merged_tickers, merged_hashtags


# X writes some crypto cashtags as "smart" tags: the post shows "$BTC" but the
# text the API returns says "bitcoin:native" (issue #216). The slug is the
# chain's coin id; these are the ones whose symbol differs from the slug.
_NATIVE_COIN_SYMBOLS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "ripple": "XRP",
    "xrp": "XRP",
    "dogecoin": "DOGE",
    "cardano": "ADA",
    "binancecoin": "BNB",
    "bnb": "BNB",
    "tron": "TRX",
    "avalanche": "AVAX",
    "polkadot": "DOT",
    "litecoin": "LTC",
    "polygon": "POL",
    "near": "NEAR",
    "sui": "SUI",
    "aptos": "APT",
    "toncoin": "TON",
    "ton": "TON",
    "stellar": "XLM",
    "cosmos": "ATOM",
    "hyperliquid": "HYPE",
    "monero": "XMR",
}

_SMART_CASHTAG_RE = re.compile(
    r"(?<![\w$])\$?([a-z0-9]+(?:-[a-z0-9]+)*):native\b", re.IGNORECASE
)


def normalize_smart_cashtags(
    text: str | None, tickers: Iterable[str] | None = None
) -> str | None:
    """Rewrite X's ``bitcoin:native`` smart cashtags to ``$BTC``.

    A slug missing from the table above takes the tweet's one ticker that the
    text doesn't already spell out as a cashtag, if there is exactly one, and
    otherwise its own uppercased name.
    """
    if not text or ":native" not in text.lower():
        return text

    written = set(extract_symbols_from_text(text)[0])
    unmatched = [t for t in _normalize(tickers, upper=True) if t not in written]

    def replace(match: re.Match[str]) -> str:
        slug = match.group(1).lower()
        symbol = _NATIVE_COIN_SYMBOLS.get(slug)
        if symbol is None:
            symbol = unmatched[0] if len(unmatched) == 1 else slug.upper()
        return f"${symbol}"

    return _SMART_CASHTAG_RE.sub(replace, text)
