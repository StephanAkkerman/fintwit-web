"""Export public tweets to sharded JSONL files for a Hugging Face dataset.

Subscriber-only posts are never exported: a row is dropped when it, or the
tweet it quotes, is flagged ``is_subscriber_only``. Rows where the flag is
unknown (NULL) are treated as public, matching the rest of the app.

The database is only read; the schema is not touched (no ``init_db``).
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import false, func, inspect, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine

from ..infra.db import TweetRow, create_engine

# Columns that are constant after filtering, or only meaningful to the live app.
_SKIP_COLUMNS = {"is_subscriber_only"}
_COLUMNS = list(TweetRow.__table__.columns)


@dataclass
class ExportStats:
    scanned: int = 0
    exported: int = 0
    skipped_subscriber: int = 0
    files: int = 0


def _is_subscriber_only(row_flag: bool | None, quoted: dict | None) -> bool:
    if row_flag:
        return True
    return isinstance(quoted, dict) and bool(quoted.get("is_subscriber_only"))


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialise(row, names: list[str]) -> str:
    record = {n: _jsonable(getattr(row, n)) for n in names if n not in _SKIP_COLUMNS}
    return json.dumps(record, ensure_ascii=False, default=str)


class _ShardWriter:
    """Writes ``tweets-00000.jsonl.gz``-style shards of at most ``size`` rows."""

    def __init__(self, out_dir: Path, size: int):
        self.out_dir, self.size = out_dir, size
        self.files = 0
        self._count = 0
        self._fh = None

    def write(self, line: str) -> None:
        if self._fh is None or self._count >= self.size:
            self.close()
            path = self.out_dir / f"tweets-{self.files:05d}.jsonl.gz"
            self._fh = gzip.open(path, "wt", encoding="utf-8")
            self.files += 1
            self._count = 0
        self._fh.write(line + "\n")
        self._count += 1

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


async def export_tweets(
    *,
    engine: AsyncEngine,
    out_dir: Path,
    batch_size: int = 5000,
    shard_size: int = 100_000,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int | None = None,
    on_progress: Callable[[ExportStats, int], None] | None = None,
) -> ExportStats:
    """Stream public tweets into ``out_dir`` ordered by tweet id (keyset paged).

    ``on_progress(stats, total)`` is called after every batch; ``total`` is the
    number of candidate rows (before the quoted-tweet check and ``limit``).
    """
    if batch_size <= 0 or shard_size <= 0:
        raise ValueError("batch_size and shard_size must be > 0")
    out_dir.mkdir(parents=True, exist_ok=True)

    def filtered(stmt):
        # Cheap first pass in SQL; quoted-tweet flag is checked per row below
        # because JSON querying differs per dialect.
        stmt = stmt.where(
            or_(
                TweetRow.is_subscriber_only.is_(None),
                TweetRow.is_subscriber_only == false(),
            )
        )
        if since is not None:
            stmt = stmt.where(TweetRow.created_at >= since)
        if until is not None:
            stmt = stmt.where(TweetRow.created_at < until)
        return stmt

    # The schema is not migrated here, so an older database may lack newer
    # columns; export whatever it has rather than failing on the rest.
    async with engine.connect() as conn:
        present = await conn.run_sync(
            lambda sync_conn: {
                c["name"] for c in inspect(sync_conn).get_columns("tweets")
            }
        )
        total = (
            await conn.execute(filtered(select(func.count()).select_from(TweetRow)))
        ).scalar_one()
    if "is_subscriber_only" not in present:
        raise RuntimeError(
            "tweets.is_subscriber_only is missing, so subscriber tweets can't be "
            "excluded. Start the app once against this database to migrate it."
        )
    columns = [c for c in _COLUMNS if c.name in present]
    names = [c.name for c in columns]
    if "quoted_tweet" not in present:
        columns.append(literal(None).label("quoted_tweet"))
    if limit is not None:
        total = min(total, limit)

    stats = ExportStats()
    writer = _ShardWriter(out_dir, shard_size)
    last_id = -1
    try:
        while limit is None or stats.exported < limit:
            stmt = (
                filtered(select(*columns))
                .where(TweetRow.id > last_id)
                .order_by(TweetRow.id)
                .limit(batch_size)
            )

            async with engine.connect() as conn:
                rows = (await conn.execute(stmt)).all()
            if not rows:
                break

            for row in rows:
                last_id = row.id
                stats.scanned += 1
                if _is_subscriber_only(row.is_subscriber_only, row.quoted_tweet):
                    stats.skipped_subscriber += 1
                    continue
                writer.write(_serialise(row, names))
                stats.exported += 1
                if limit is not None and stats.exported >= limit:
                    break
            if on_progress is not None:
                on_progress(stats, total)
    finally:
        writer.close()
    stats.files = writer.files
    return stats


async def export_subscriber_ids(
    *, engine: AsyncEngine, path: Path, batch_size: int = 5000
) -> int:
    """Write the id of every subscriber-only tweet to ``path``, one per line.

    Uses the same rule as the export (the tweet or the one it quotes), so the
    list can be used to filter other collections of the same tweets.
    """
    async with engine.connect() as conn:
        present = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("tweets")}
        )
    if "is_subscriber_only" not in present:
        raise RuntimeError(
            "tweets.is_subscriber_only is missing; start the app once against this "
            "database to migrate it."
        )
    has_quoted = "quoted_tweet" in present
    quoted_col = TweetRow.quoted_tweet if has_quoted else literal(None)

    count = 0
    last_id = -1
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        while True:
            stmt = (
                select(TweetRow.id, TweetRow.is_subscriber_only, quoted_col)
                .where(TweetRow.id > last_id)
                .where(
                    or_(
                        TweetRow.is_subscriber_only.is_(True),
                        # Only these rows can be flagged through the quoted tweet
                        *([TweetRow.quoted_tweet.is_not(None)] if has_quoted else []),
                    )
                )
                .order_by(TweetRow.id)
                .limit(batch_size)
            )
            async with engine.connect() as conn:
                rows = (await conn.execute(stmt)).all()
            if not rows:
                return count
            for tweet_id, flag, quoted in rows:
                last_id = tweet_id
                if _is_subscriber_only(flag, quoted):
                    fh.write(f"{tweet_id}\n")
                    count += 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export public (non-subscriber) tweets to JSONL for Hugging Face"
    )
    parser.add_argument(
        "--db-url",
        default=os.getenv("DB_URL", "sqlite+aiosqlite:///./data.db"),
        help="Database URL used by SQLAlchemy (async driver, e.g. "
        "sqlite+aiosqlite:/// or postgresql+asyncpg://)",
    )
    parser.add_argument("--out", default="export", help="Output directory")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument(
        "--shard-size", type=int, default=100_000, help="Max rows per .jsonl.gz file"
    )
    parser.add_argument("--since", type=datetime.fromisoformat, help="created_at >= ")
    parser.add_argument("--until", type=datetime.fromisoformat, help="created_at < ")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to export")
    parser.add_argument(
        "--quiet", action="store_true", help="Don't print progress while exporting"
    )
    parser.add_argument(
        "--subscriber-ids",
        metavar="FILE",
        help="Instead of exporting, write the ids of subscriber-only tweets to FILE "
        "(for filtering other copies of the same tweets, e.g. fintwit-bot's)",
    )
    parser.add_argument(
        "--push-to",
        metavar="REPO_ID",
        help="Upload the output directory to this HF dataset repo, e.g. user/fintwit "
        "(needs `pip install huggingface_hub` and HF_TOKEN or `hf auth login`)",
    )
    parser.add_argument(
        "--private", action="store_true", help="Create the HF repo as private"
    )
    return parser


def _push(out_dir: Path, repo_id: str, private: bool) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo_id, repo_type="dataset", private=private, exist_ok=True)
    api.upload_folder(
        folder_path=str(out_dir),
        repo_id=repo_id,
        repo_type="dataset",
        path_in_repo="data",
        allow_patterns=["*.jsonl.gz"],
        commit_message="Update tweets export",
    )


class _ProgressPrinter:
    """Progress line on stderr: a live-updating bar on a TTY, else periodic lines."""

    def __init__(self) -> None:
        self.start = time.monotonic()
        self.tty = sys.stderr.isatty()

    def __call__(self, stats: ExportStats, total: int) -> None:
        elapsed = max(time.monotonic() - self.start, 1e-6)
        rate = stats.scanned / elapsed
        pct = min(stats.scanned / total, 1.0) if total else 1.0
        eta = (total - stats.scanned) / rate if total > stats.scanned else 0
        filled = int(pct * 30)
        line = (
            f"[export] |{'#' * filled}{'-' * (30 - filled)}| {pct:6.1%} "
            f"{stats.exported:,}/{total:,} exported, "
            f"{stats.skipped_subscriber:,} subscriber skipped, "
            f"{rate:,.0f} rows/s, ETA {int(eta // 60)}m{int(eta % 60):02d}s"
        )
        if self.tty:
            print("\r" + line, end="", file=sys.stderr, flush=True)
        else:
            print(line, file=sys.stderr, flush=True)

    def finish(self) -> None:
        if self.tty:
            print(file=sys.stderr)


async def _run(args: argparse.Namespace) -> int:
    engine = create_engine(args.db_url)
    if args.subscriber_ids:
        try:
            count = await export_subscriber_ids(
                engine=engine, path=Path(args.subscriber_ids)
            )
        finally:
            await engine.dispose()
        print(f"[export] {count} subscriber-only tweet ids -> {args.subscriber_ids}")
        return 0
    progress = _ProgressPrinter()
    try:
        stats = await export_tweets(
            engine=engine,
            out_dir=Path(args.out),
            batch_size=args.batch_size,
            shard_size=args.shard_size,
            since=args.since,
            until=args.until,
            limit=args.limit,
            on_progress=None if args.quiet else progress,
        )
    finally:
        await engine.dispose()
        progress.finish()

    print(f"[export] scanned={stats.scanned}")
    print(f"[export] skipped_subscriber={stats.skipped_subscriber}")
    print(f"[export] exported={stats.exported} files={stats.files} -> {args.out}")
    if args.push_to:
        _push(Path(args.out), args.push_to, args.private)
        print(f"[export] uploaded to https://huggingface.co/datasets/{args.push_to}")
    return 0


def main() -> int:
    return asyncio.run(_run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
