# Exporting tweets to a Hugging Face dataset

`app/runtime/export_dataset.py` streams the `tweets` table into gzipped JSONL
shards, optionally uploading them to a Hugging Face dataset repo. It only
reads the database (it does not run schema migrations), so it is safe to point
at production.

## What is excluded

A tweet is dropped when **either**:

- its own `is_subscriber_only` flag is true, or
- the tweet it quotes has `quoted_tweet.is_subscriber_only` true (the quoted
  text is embedded in the row, so it would leak otherwise).

Rows where the flag is `NULL` (never determined) are treated as public, the
same as the rest of the app. If you want to be stricter, check how many you
have first:

```sql
SELECT COUNT(*) FROM tweets WHERE is_subscriber_only IS NULL;
```

The `is_subscriber_only` column itself is omitted from the output, since it is
constant after filtering.

## Usage

```bash
# Install the optional upload dependency (only needed for --push-to)
pip install huggingface_hub

# Local export only
python -m app.runtime.export_dataset --db-url "sqlite+aiosqlite:///./data.db" --out export

# Export and upload (private repo first, so you can inspect before publishing)
export HF_TOKEN=hf_xxx            # or: hf auth login
python -m app.runtime.export_dataset --out export --push-to youruser/fintwit-tweets --private
```

| Flag | Default | Meaning |
|---|---|---|
| `--db-url` | `$DB_URL` or `sqlite+aiosqlite:///./data.db` | Needs an async driver (`postgresql+asyncpg://...` for Postgres) |
| `--out` | `export` | Output directory, created if missing |
| `--shard-size` | `100000` | Rows per `tweets-NNNNN.jsonl.gz` file |
| `--batch-size` | `5000` | Rows fetched per query (keyset-paged by tweet id) |
| `--since` / `--until` | none | ISO datetimes filtering on `created_at` (`>=` / `<`) |
| `--limit` | none | Stop after N exported rows (good for a trial run) |
| `--quiet` | off | Hide the progress output |
| `--subscriber-ids FILE` | none | Write the ids of subscriber-only tweets to FILE and exit, instead of exporting. Feed it to fintwit-bot's `upload_hf.py --exclude-ids` |
| `--push-to` | none | HF repo id; files land under `data/` |
| `--private` | off | Create the repo as private |

While running, a progress bar goes to stderr (percent, exported and skipped
counts, rows/s, ETA). In a terminal it updates in place; when redirected to a
log file it prints one line per batch. The total comes from a `COUNT(*)` up
front, which can take a moment on a large table. At the end it prints
`scanned`, `skipped_subscriber` and `exported` counts.

### Scraping a production database

Run it where the database is reachable. For a SQLite file on a server, either
run the command there, or copy a consistent snapshot and export locally:

```bash
ssh prod 'sqlite3 /path/to/data.db ".backup /tmp/snapshot.db"'
scp prod:/tmp/snapshot.db ./snapshot.db
python -m app.runtime.export_dataset --db-url "sqlite+aiosqlite:///./snapshot.db"
```

Copying `data.db` directly while the app is writing can give a corrupt copy;
use `.backup`. With Postgres, point `--db-url` at a read replica if you have
one.

## Before publishing

1. Do a `--limit 1000` run and read the output; confirm no subscriber text is
   present (`zcat export/tweets-00000.jsonl.gz | head`).
2. Check the content rights: X's developer terms restrict redistributing full
   tweet content, and many datasets publish only tweet IDs for that reason.
   If that applies to you, drop `text`, `quoted_tweet` and `image_text` from
   the output and let consumers rehydrate from the `id`/`url`.
3. Upload as private first, then flip the repo to public in the HF settings.

## Loading the result

```python
from datasets import load_dataset

ds = load_dataset("youruser/fintwit-tweets", split="train")
```

Columns like `tickers`, `assets` and `quoted_tweet` are nested JSON.
`assets` holds price snapshots taken at ingest time, not current prices.
