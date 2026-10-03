"""Extract historical tweets matching regex filters, e.g. for model training data.

Examples
--------
    python -m app.runtime.scrape_tweets --list-presets
    python -m app.runtime.scrape_tweets --preset options --out options.jsonl
    python -m app.runtime.scrape_tweets -e '\\d+\\s*C\\s+\\d{1,2}/\\d{1,2}' --stats
    python -m app.runtime.scrape_tweets --preset options --exclude 'giveaway' \\
        --since 2026-06-01 --format csv --out options.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import TextIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..infra.db import TweetRow, create_engine

# Named patterns for the ways options flow shows up on fintwit. Each is matched
# case-insensitively; "options" is the union of all of them.
_CP = r"(?:calls?|puts?|[CP])"
PRESETS: dict[str, str] = {
    # "350 C 11/06/2026", "172.5 Call (10/23)", "15 Call (11/20)"
    "strike-expiry": (
        rf"\d+(?:\.\d+)?\s*{_CP}\b(?:\s+strike)?[\s(\-]*(?:(?:for|exp)\s+)?"
        r"\(?\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    ),
    # "10/16 44c", "5/15 19c"
    "expiry-strike": rf"\b\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?\)?\s*\d+(?:\.\d+)?\s*{_CP}\b",
    # "$AAPL 350 C", "$ANET 155 Call", "$FSLR 220 calls"
    "ticker-strike": rf"\$[A-Za-z]{{1,5}}\s+\$?\d+(?:\.\d+)?\s*{_CP}\b",
    # "$1200 calls on $MU", "220 calls for $FSLR"
    "strike-on-ticker": (
        r"\$?\d+(?:\.\d+)?\s*(?:calls?|puts?)\s+(?:on|for)\s+\$[A-Za-z]{1,5}"
    ),
    # "$446K Call buyer", "$5.5M on $FSLR 220 calls", "call buyers coming in"
    "premium": (
        r"\$\d+(?:\.\d+)?[KMB]\s+(?:\w+\s+)?(?:\$?[A-Za-z]{1,5}\s+)?(?:calls?|puts?)\b"
        r"|\b(?:calls?|puts?)\s+(?:buyers?|sellers?)\b"
    ),
}
PRESETS["options"] = "|".join(f"(?:{p})" for p in PRESETS.values())


def compile_filters(
    patterns: Sequence[str] = (),
    presets: Sequence[str] = (),
    *,
    ignore_case: bool = True,
) -> list[tuple[str, re.Pattern[str]]]:
    """Compile preset names and raw regexes into labelled patterns.

    Raises
    ------
    ValueError
        On an unknown preset name or a regex that does not compile.
    """
    flags = re.IGNORECASE if ignore_case else 0
    out: list[tuple[str, re.Pattern[str]]] = []
    for name in presets:
        if name not in PRESETS:
            raise ValueError(
                f"unknown preset {name!r}; available: {', '.join(sorted(PRESETS))}"
            )
        out.append((name, re.compile(PRESETS[name], flags | re.IGNORECASE)))
    for pattern in patterns:
        try:
            out.append((pattern, re.compile(pattern, flags)))
        except re.error as exc:
            raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc
    return out


def text_matches(
    text: str,
    include: Sequence[tuple[str, re.Pattern[str]]],
    exclude: Sequence[tuple[str, re.Pattern[str]]] = (),
    *,
    match_all: bool = False,
) -> list[str]:
    """Return the labels of matching include filters; ``[]`` means no match.

    ``match_all`` requires every include filter to match instead of any.
    Any exclude filter matching rejects the tweet.
    """
    if any(p.search(text) for _, p in exclude):
        return []
    hits = [label for label, p in include if p.search(text)]
    if match_all and len(hits) != len(include):
        return []
    return hits


_QUOTE_START = re.compile(r"^>\s*\[@", re.MULTILINE)


def split_quoted(text: str) -> tuple[str, str]:
    r"""Split a tweet into its own text and the quoted tweet embedded in it.

    A quote tweet is stored as ``own text\n\n> [@user](url):\n> quoted...``; the
    quote runs to the end of the text. Returns ``(own, quoted)``.
    """
    m = _QUOTE_START.search(text)
    if not m:
        return text, ""
    return text[: m.start()].rstrip(), text[m.start() :]


def _fingerprint(text: str) -> str:
    return " ".join(text.lower().split())


async def iter_matching_tweets(
    session_factory: async_sessionmaker,
    include: Sequence[tuple[str, re.Pattern[str]]],
    exclude: Sequence[tuple[str, re.Pattern[str]]] = (),
    *,
    match_all: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    dedupe: bool = True,
    include_quoted: bool = False,
    limit: int | None = None,
    batch_size: int = 1000,
) -> AsyncIterator[dict]:
    """Scan tweets newest-first (keyset-paginated) and yield matching rows.

    ``dedupe`` drops tweets whose whitespace/case-normalised text was already
    yielded, which collapses retweets and repeated alerts so a training set is
    not skewed by copies of the same line.

    Filters match only the tweet's own text: a quoted tweet is someone else's
    words and would otherwise make an unrelated reply look like a match. The
    quote is still returned in ``quoted_text``; ``include_quoted`` matches it too.
    """
    seen: set[str] = set()
    yielded = 0
    last_id: int | None = None
    while True:
        stmt = (
            select(
                TweetRow.id,
                TweetRow.text,
                TweetRow.url,
                TweetRow.user_screen_name,
                TweetRow.created_at,
                TweetRow.tickers,
                TweetRow.image_text,
                TweetRow.is_options_tweet,
            )
            .order_by(TweetRow.id.desc())
            .limit(batch_size)
        )
        if last_id is not None:
            stmt = stmt.where(TweetRow.id < last_id)
        if since is not None:
            stmt = stmt.where(TweetRow.created_at >= since)
        if until is not None:
            stmt = stmt.where(TweetRow.created_at < until)
        async with session_factory() as session:
            rows = (await session.execute(stmt)).all()
        if not rows:
            return
        last_id = rows[-1].id
        for row in rows:
            full = row.text or ""
            text, quoted = split_quoted(full)
            hits = text_matches(
                full if include_quoted else text, include, exclude, match_all=match_all
            )
            if not hits:
                continue
            if dedupe:
                key = _fingerprint(text)
                if key in seen:
                    continue
                seen.add(key)
            yield {
                "id": str(row.id),
                "url": row.url,
                "user": row.user_screen_name,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "text": text,
                "quoted_text": quoted,
                "tickers": row.tickers or [],
                "image_text": row.image_text,
                "is_options_tweet": bool(row.is_options_tweet),
                "matched": hits,
            }
            yielded += 1
            if limit is not None and yielded >= limit:
                return


def write_records(records: Sequence[dict], out: TextIO, fmt: str) -> None:
    """Write records as JSON Lines or CSV (list fields JSON-encoded)."""
    if fmt == "jsonl":
        for rec in records:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return
    fields = list(records[0]) if records else ["id", "text"]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for rec in records:
        writer.writerow(
            {
                k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v
                for k, v in rec.items()
            }
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract historical tweets matching regex filters"
    )
    parser.add_argument(
        "--db-url",
        default=os.getenv("DB_URL", "sqlite+aiosqlite:///./data.db"),
        help="Database URL used by SQLAlchemy",
    )
    parser.add_argument(
        "-e",
        "--regex",
        action="append",
        default=[],
        help="Regex to match against tweet text (repeatable)",
    )
    parser.add_argument(
        "-p",
        "--preset",
        action="append",
        default=[],
        help="Named pattern, see --list-presets (repeatable)",
    )
    parser.add_argument(
        "-x",
        "--exclude",
        action="append",
        default=[],
        help="Regex that rejects a tweet when it matches (repeatable)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Require every -e/-p filter to match (default: any)",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Match user regexes case-sensitively (presets always ignore case)",
    )
    parser.add_argument("--since", type=datetime.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--until", type=datetime.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--limit", type=int, help="Stop after this many matches")
    parser.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="Keep tweets whose text duplicates an earlier match",
    )
    parser.add_argument(
        "--include-quoted",
        action="store_true",
        help="Also match against the quoted tweet embedded in a quote tweet",
    )
    parser.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    parser.add_argument("--out", help="Output file (default: stdout)")
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print match counts per filter to stderr instead of writing output",
    )
    parser.add_argument(
        "--list-presets", action="store_true", help="Show preset patterns and exit"
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.list_presets:
        for name, pattern in PRESETS.items():
            print(f"{name}\n    {pattern}")
        return 0

    presets = args.preset or ([] if args.regex else ["options"])
    try:
        include = compile_filters(
            args.regex, presets, ignore_case=not args.case_sensitive
        )
        exclude = compile_filters(args.exclude, ignore_case=not args.case_sensitive)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    engine = create_engine(args.db_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        records = [
            rec
            async for rec in iter_matching_tweets(
                factory,
                include,
                exclude,
                match_all=args.all,
                since=args.since,
                until=args.until,
                dedupe=not args.keep_duplicates,
                include_quoted=args.include_quoted,
                limit=args.limit,
            )
        ]
    finally:
        await engine.dispose()

    if args.stats:
        counts = {label: 0 for label, _ in include}
        for rec in records:
            for label in rec["matched"]:
                counts[label] += 1
        print(f"{len(records)} matching tweets", file=sys.stderr)
        for label, n in counts.items():
            print(f"  {n:6d}  {label}", file=sys.stderr)
        return 0

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="") as fh:
            write_records(records, fh, args.format)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        write_records(records, sys.stdout, args.format)
    print(f"wrote {len(records)} tweets", file=sys.stderr)
    return 0


def main() -> int:
    return asyncio.run(_run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
