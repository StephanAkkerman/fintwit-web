import xclient

from app.runtime.xclient_compat import apply_xclient_retweet_patch


def _mock_user(name: str, screen_name: str, image_url: str) -> dict:
    return {
        "core": {
            "user_results": {
                "result": {
                    "core": {
                        "name": name,
                        "screen_name": screen_name,
                    },
                    "avatar": {
                        "image_url": image_url,
                    },
                }
            }
        }
    }


def _mock_tweet(rest_id: int, name: str, screen_name: str, image_url: str, text: str):
    return {
        "rest_id": str(rest_id),
        "core": _mock_user(name, screen_name, image_url)["core"],
        "legacy": {
            "id_str": str(rest_id),
            "full_text": text,
            "entities": {"urls": [], "symbols": [], "hashtags": []},
            "favorite_count": 1,
            "retweet_count": 1,
            "reply_count": 1,
            "created_at": "Tue Apr 08 12:00:00 +0000 2026",
        },
        "views": {"count": "10"},
    }


def test_retweet_parser_patch_attaches_original_tweet_metadata():
    apply_xclient_retweet_patch()
    client = xclient.XTimelineClient("curl.txt")

    original = _mock_tweet(
        2002,
        "Original Poster",
        "orig",
        "https://example.com/original.jpg",
        "Original post body",
    )
    repost_wrapper = _mock_tweet(
        3003,
        "Repost Account",
        "reposter",
        "https://example.com/reposter.jpg",
        "Wrapper text",
    )
    repost_wrapper["legacy"]["retweeted_status_result"] = {"result": original}

    parsed = client._parse_single_tweet(repost_wrapper)

    assert parsed is not None
    assert parsed.user_name == "Repost Account"
    assert parsed.quoted_tweet is not None
    assert parsed.quoted_tweet.user_name == "Original Poster"
    assert parsed.quoted_tweet.user_screen_name == "orig"
    assert parsed.quoted_tweet.user_img == "https://example.com/original.jpg"
