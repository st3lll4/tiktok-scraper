"""
TikTok comment scraper using Playwright.

Strategy: Open the video page, intercept TikTok's internal API responses for
comments and replies, scroll to trigger lazy-loading until all comments are
collected. This gives us structured JSON directly from TikTok's API while
Playwright handles cookies, tokens, and anti-bot measures.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright, Page, BrowserContext


def _parse_timestamp(ts: int | float) -> str:
    """Convert a unix timestamp to a human-readable UTC string."""
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def _extract_video_id(url: str) -> str:
    """Pull the numeric video ID from a TikTok URL."""
    match = re.search(r"/video/(\d+)", url)
    if match:
        return match.group(1)
    # Fallback: use last path segment
    return url.rstrip("/").split("/")[-1]


def _parse_comment(comment: dict, reply_to_user: str = "") -> dict:
    """Turn a raw API comment object into a flat row."""
    user_info = comment.get("user", {})
    username = (
        user_info.get("unique_id")
        or user_info.get("uniqueId")
        or user_info.get("nickname", "unknown")
    )
    text = comment.get("text", comment.get("comment", ""))
    create_time = comment.get("create_time", comment.get("createTime", 0))

    return {
        "username": username,
        "comment": text,
        "reply_to": reply_to_user,
        "timestamp": _parse_timestamp(create_time),
        "unix_timestamp": int(create_time),
    }


def _collect_from_api_response(data: dict, rows: list[dict], seen_ids: set):
    """Parse a TikTok comments API response and append new rows."""
    comments = data.get("comments", [])
    for c in comments:
        cid = str(c.get("cid", c.get("id", "")))
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        parent_username = ""
        row = _parse_comment(c, reply_to_user=parent_username)
        rows.append(row)

        # Inline replies that come nested under the parent comment
        for reply in c.get("reply_comment", []):
            rid = str(reply.get("cid", reply.get("id", "")))
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            reply_row = _parse_comment(reply, reply_to_user=row["username"])
            rows.append(reply_row)


def _collect_from_reply_response(
    data: dict, rows: list[dict], seen_ids: set, parent_username: str
):
    """Parse a TikTok reply-list API response."""
    comments = data.get("comments", [])
    for c in comments:
        cid = str(c.get("cid", c.get("id", "")))
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        row = _parse_comment(c, reply_to_user=parent_username)
        rows.append(row)


def scrape_video(
    url: str,
    output_dir: str = "output",
    max_comments: int = 50000,
    scroll_timeout: int = 5,
    headless: bool = True,
) -> Path:
    """
    Scrape comments from a single TikTok video.

    Returns the path to the generated CSV file.
    """
    video_id = _extract_video_id(url)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_path = output_path / f"comments_{video_id}.csv"

    rows: list[dict] = []
    seen_ids: set = set()
    # Map comment_id -> username so we can label replies
    parent_map: dict[str, str] = {}

    print(f"[scraper] Starting scrape for video {video_id}")
    print(f"[scraper] URL: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()

        # Intercept comment API responses
        def handle_response(response):
            resp_url = response.url
            try:
                if "comment/list" in resp_url and response.status == 200:
                    data = response.json()
                    _collect_from_api_response(data, rows, seen_ids)
                    # Build parent map for reply lookups
                    for c in data.get("comments", []):
                        cid = str(c.get("cid", c.get("id", "")))
                        user = c.get("user", {})
                        uname = (
                            user.get("unique_id")
                            or user.get("uniqueId")
                            or user.get("nickname", "unknown")
                        )
                        parent_map[cid] = uname

                elif "comment/list/reply" in resp_url and response.status == 200:
                    data = response.json()
                    # Figure out parent username from the request URL
                    parent_id_match = re.search(
                        r"comment_id=(\d+)", resp_url
                    )
                    parent_user = ""
                    if parent_id_match:
                        parent_user = parent_map.get(
                            parent_id_match.group(1), ""
                        )
                    _collect_from_reply_response(
                        data, rows, seen_ids, parent_user
                    )
            except Exception:
                pass  # Non-JSON or unexpected format, skip

        page.on("response", handle_response)

        # Navigate to the video
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Wait for comments section to appear
        try:
            page.wait_for_selector(
                "[class*='CommentListContainer'], [class*='comment-list'], "
                "[data-e2e='comment-list']",
                timeout=15000,
            )
        except Exception:
            print("[scraper] Comment section not found via selector, will try scrolling anyway")

        time.sleep(2)

        # Scroll the comments panel to load more
        prev_count = 0
        stale_rounds = 0
        max_stale = 8  # Stop after this many scrolls with no new comments

        print("[scraper] Scrolling to load comments...")

        while len(rows) < max_comments and stale_rounds < max_stale:
            # Try scrolling the comment container, fall back to page scroll
            page.evaluate("""
                const containers = document.querySelectorAll(
                    '[class*="CommentListContainer"], [class*="comment-list"], [data-e2e="comment-list"]'
                );
                if (containers.length > 0) {
                    containers[0].scrollTop = containers[0].scrollHeight;
                }
                window.scrollBy(0, 800);
            """)

            # Click "View more replies" buttons if present
            try:
                reply_buttons = page.query_selector_all(
                    '[data-e2e="view-more-replies"], '
                    '[class*="ReplyActionText"], '
                    'p:has-text("View"), span:has-text("View")'
                )
                for btn in reply_buttons[:5]:  # Click a few at a time
                    try:
                        btn.click(timeout=1000)
                        time.sleep(0.3)
                    except Exception:
                        pass
            except Exception:
                pass

            time.sleep(scroll_timeout)

            if len(rows) == prev_count:
                stale_rounds += 1
            else:
                stale_rounds = 0
            prev_count = len(rows)
            print(f"[scraper] Comments collected so far: {len(rows)}")

        browser.close()

    if not rows:
        print("[scraper] WARNING: No comments were captured. The video may have comments disabled or TikTok blocked the request.")
        # Write empty CSV with headers
        df = pd.DataFrame(columns=["username", "comment", "reply_to", "timestamp"])
        df.to_csv(csv_path, index=False)
        return csv_path

    df = pd.DataFrame(rows)
    # Sort by timestamp
    df = df.sort_values("unix_timestamp").reset_index(drop=True)
    # Keep only human-readable columns in the final CSV
    df = df[["username", "comment", "reply_to", "timestamp"]]
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"[scraper] Done! {len(df)} comments saved to {csv_path}")
    return csv_path
