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
