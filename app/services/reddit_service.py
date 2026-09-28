from __future__ import annotations

import argparse
import html
import logging
import os
import re
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

URL_REGEX = r"(?P<url>https?://[^\s]+)"
MARKDOWN_LINK_REGEX = r"\[(?P<text>[^\]]+)\]\((?P<url>https?://[^\s]+)\)"
SUBREDDIT_NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")

_HEADERS = {
    "User-Agent": "fintwit-web/0.1 (+https://github.com/StephanAkkerman/fintwit-web)",
    "Accept": "application/json",
}


def is_valid_subreddit_name(name: str) -> bool:
    return bool(SUBREDDIT_NAME_RE.match(name or ""))


def truncate_text(text: str, max_length: int) -> str:
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def process_description(description: str) -> str:
    def replace_markdown_link(match: re.Match[str]) -> str:
        text = match.group("text")
        url = match.group("url")
        if text == url:
            return url
        return match.group(0)

    description = re.sub(MARKDOWN_LINK_REGEX, replace_markdown_link, description)

    def replace_url(match: re.Match[str]) -> str:
        return match.group("url")

    return re.sub(URL_REGEX, replace_url, description)


_IMAGE_SUFFIXES = (".jpg", ".png", ".gif", ".jpeg", ".webp")


def _preview_image(submission: dict) -> str | None:
    """Reddit's own preview of a post's link or video, when it generated one."""
    preview_images = (submission.get("preview") or {}).get("images") or []
    if not preview_images:
        return None
    source = (preview_images[0] or {}).get("source") or {}
    img = source.get("url")
    return html.unescape(str(img)) if img else None


def process_submission_media(submission: dict) -> tuple[list[str], str | None]:
    """Collect a post's images and classify its media.

    :return: ``(image_urls, media_type)`` where ``media_type`` is ``"image"``,
        ``"gallery"``, ``"video"``, ``"link"`` or ``None`` for a text post.
        The Discord bot marked these with an ``IMG``/``GALLERY``/``VIDEO``
        title prefix because an embed had nowhere else to say it; the web UI
        renders the preview itself, so the title stays as the author wrote it.
    """
    image_urls: list[str] = []

    if submission.get("is_self"):
        return image_urls, None

    url = str(submission.get("url") or "")
    normalized_url = html.unescape(url)

    if normalized_url.lower().endswith(_IMAGE_SUFFIXES):
        image_urls.append(normalized_url)
        return image_urls, "image"

    if submission.get("is_gallery"):
        media_metadata = submission.get("media_metadata") or {}
        for item in media_metadata.values():
            source = (item or {}).get("s") or {}
            img = source.get("u")
            if img:
                image_urls.append(html.unescape(str(img)))
        return image_urls, "gallery"

    preview = _preview_image(submission)
    if preview:
        image_urls.append(preview)
    if "v.redd.it" in normalized_url or submission.get("is_video"):
        return image_urls, "video"
    return image_urls, "link"


def _reddit_credentials_from_env() -> dict[str, str] | None:
    """Load Reddit API credentials using legacy and modern env var names."""
    client_id = os.getenv("REDDIT_CLIENT_ID") or os.getenv("REDDIT_PERSONAL_USE")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET") or os.getenv("REDDIT_SECRET")
    user_agent = (
        os.getenv("REDDIT_USER_AGENT")
        or os.getenv("REDDIT_APP_NAME")
        or _HEADERS["User-Agent"]
    )

    if not client_id or not client_secret:
        return None

    creds = {
        "client_id": client_id,
        "client_secret": client_secret,
        "user_agent": user_agent,
    }

    username = os.getenv("REDDIT_USERNAME")
    password = os.getenv("REDDIT_PASSWORD")
    if username and password:
        creds["username"] = username
        creds["password"] = password

    return creds


def has_reddit_credentials() -> bool:
    """Whether Reddit API credentials are configured in the environment."""
    return _reddit_credentials_from_env() is not None


def _normalize_post_payload(data: dict[str, Any], subreddit_name: str) -> dict:
    description = truncate_text(html.unescape(str(data.get("selftext") or "")), 4000)
    description = process_description(description)

    title = truncate_text(html.unescape(str(data.get("title") or "")), 250)
    image_urls, media_type = process_submission_media(data)

    permalink = str(data.get("permalink") or "")
    post_url = (
        f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
    )

    return {
        "id": str(data.get("id") or ""),
        "subreddit": str(data.get("subreddit") or subreddit_name),
        "title": title,
        "description": description,
        "author": str(data.get("author") or ""),
        "score": int(data.get("score") or 0),
        "num_comments": int(data.get("num_comments") or 0),
        "created_utc": int(data.get("created_utc") or 0),
        "url": post_url,
        "image_urls": image_urls,
        "media_type": media_type,
        # The external page a link post points at (None for self/media posts,
        # whose `url` is the Reddit thread itself).
        "link_url": (
            html.unescape(str(data.get("url") or "")) if media_type == "link" else None
        ),
        "flair": str(data.get("link_flair_text") or "") or None,
        "upvote_ratio": float(data.get("upvote_ratio") or 0.0) or None,
        "over_18": bool(data.get("over_18")),
    }


def _submission_to_dict(submission: Any) -> dict[str, Any]:
    return {
        "id": getattr(submission, "id", ""),
        "subreddit": str(getattr(submission, "subreddit", "")),
        "title": getattr(submission, "title", ""),
        "selftext": getattr(submission, "selftext", ""),
        "author": str(getattr(submission, "author", "")),
        "score": getattr(submission, "score", 0),
        "num_comments": getattr(submission, "num_comments", 0),
        "created_utc": getattr(submission, "created_utc", 0),
        "permalink": getattr(submission, "permalink", ""),
        "is_self": getattr(submission, "is_self", True),
        "stickied": getattr(submission, "stickied", False),
        "url": getattr(submission, "url", ""),
        "is_gallery": getattr(submission, "is_gallery", False),
        "media_metadata": getattr(submission, "media_metadata", None),
        "preview": getattr(submission, "preview", None),
        "is_video": getattr(submission, "is_video", False),
        "link_flair_text": getattr(submission, "link_flair_text", None),
        "upvote_ratio": getattr(submission, "upvote_ratio", None),
        "over_18": getattr(submission, "over_18", False),
    }


async def _fetch_with_asyncpraw(
    subreddit_name: str,
    limit: int,
    debug: bool = False,
) -> list[dict] | None:
    try:
        import asyncpraw  # type: ignore
    except ImportError:
        if debug:
            logger.info("[reddit] asyncpraw not installed, skipping package path")
        return None

    creds = _reddit_credentials_from_env()
    if creds is None:
        if debug:
            logger.info(
                "[reddit] no Reddit credentials found in env, skipping asyncpraw"
            )
        return None

    if debug:
        logger.info(
            "[reddit] using asyncpraw for subreddit=%s limit=%s", subreddit_name, limit
        )

    reddit = asyncpraw.Reddit(**creds)
    try:
        subreddit = await reddit.subreddit(subreddit_name)
        posts: list[dict] = []
        async for submission in subreddit.hot(limit=limit):
            data = _submission_to_dict(submission)
            if data.get("stickied"):
                continue
            posts.append(_normalize_post_payload(data, subreddit_name))
        if debug:
            logger.info("[reddit] asyncpraw returned %s posts", len(posts))
        return posts
    except Exception as exc:
        logger.warning(
            "[reddit] asyncpraw fetch failed, falling back to httpx: %r", exc
        )
        return None
    finally:
        with suppress(Exception):
            await reddit.close()


async def _fetch_with_httpx(
    client: httpx.AsyncClient,
    subreddit_name: str,
    limit: int,
    debug: bool = False,
) -> list[dict] | None:
    url = f"https://www.reddit.com/r/{subreddit_name}/hot.json"
    if debug:
        logger.info("[reddit] using httpx fallback url=%s", url)
    response = await client.get(
        url,
        params={"limit": limit, "raw_json": 1},
        headers=_HEADERS,
    )
    if response.status_code != 200:
        if debug:
            logger.warning("[reddit] httpx fallback status=%s", response.status_code)
        return None

    payload = response.json()
    children = ((payload or {}).get("data") or {}).get("children") or []

    posts: list[dict] = []
    for child in children:
        data = (child or {}).get("data") or {}
        if data.get("stickied"):
            continue
        posts.append(_normalize_post_payload(data, subreddit_name))

    if debug:
        logger.info("[reddit] httpx fallback returned %s posts", len(posts))

    return posts


async def get_reddit_hot_posts(
    client: httpx.AsyncClient,
    subreddit_name: str = "wallstreetbets",
    limit: int = 15,
    debug: bool = False,
) -> list[dict] | None:
    if not is_valid_subreddit_name(subreddit_name):
        if debug:
            logger.warning("[reddit] invalid subreddit name: %r", subreddit_name)
        return None

    # Keep limits bounded even when called outside API-layer validation.
    bounded_limit = max(1, min(int(limit), 50))

    try:
        praw_posts = await _fetch_with_asyncpraw(
            subreddit_name, bounded_limit, debug=debug
        )
        if praw_posts is not None:
            return praw_posts

        return await _fetch_with_httpx(
            client, subreddit_name, bounded_limit, debug=debug
        )
    except (httpx.RequestError, ValueError, TypeError, KeyError) as exc:
        logger.exception("Could not fetch or process Reddit data: %r", exc)
        return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reddit WallStreetBets fetch smoke test"
    )
    parser.add_argument("--subreddit", default="wallstreetbets")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    return parser


if __name__ == "__main__":
    import asyncio

    # Load the .env vars
    from dotenv import load_dotenv

    root_env = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(dotenv_path=root_env, override=True)

    async def main(args: argparse.Namespace):
        logging.basicConfig(
            level=logging.DEBUG if args.debug else logging.INFO,
            format="%(levelname)s | %(name)s | %(message)s",
        )
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        if not args.debug:
            logging.getLogger("httpx").setLevel(logging.WARNING)

        has_creds = _reddit_credentials_from_env() is not None
        logger.info("[reddit] credentials configured: %s", has_creds)
        logger.info("[reddit] subreddit=%s limit=%s", args.subreddit, args.limit)

        async with httpx.AsyncClient() as client:
            posts = await get_reddit_hot_posts(
                client,
                args.subreddit,
                limit=args.limit,
                debug=args.debug,
            )

            if posts is None:
                print(
                    "No posts fetched (service unavailable / blocked / invalid config)."
                )
                return

            print(f"Fetched {len(posts)} posts.")
            for idx, post in enumerate(posts[:5], start=1):
                print(f"{idx}. {post.get('title', '')}")

    cli_args = _build_parser().parse_args()
    asyncio.run(main(cli_args))
