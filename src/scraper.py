"""
TikTok comment scraper using Playwright.

Strategy: Use Playwright to visit the TikTok page and obtain valid session
cookies, then call TikTok's internal comment API directly with those cookies
to fetch all comments and replies. This bypasses the need for the page to
fully render the comment section.
"""

import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright


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


def _fetch_comments_via_api(page, video_id: str, max_comments: int) -> list[dict]:
    """
    Use the browser's fetch() to call TikTok's comment API directly.
    This runs inside the page context so cookies and headers are automatically included.
    """
    rows = []
    seen_ids = set()
    cursor = 0
    count = 50  # Comments per request
    has_more = True
    consecutive_failures = 0

    print("[scraper] Fetching comments via API...")

    while has_more and len(rows) < max_comments and consecutive_failures < 3:
        # Use the aid=1988 parameter which works more reliably
        api_url = (
            f"https://www.tiktok.com/api/comment/list/"
            f"?aid=1988"
            f"&aweme_id={video_id}"
            f"&cursor={cursor}"
            f"&count={count}"
            f"&current_region=US"
        )

        try:
            result = page.evaluate(f"""
                async () => {{
                    const resp = await fetch("{api_url}", {{
                        credentials: 'include',
                    }});
                    return await resp.json();
                }}
            """)
        except Exception as e:
            print(f"[scraper] API call failed: {e}")
            consecutive_failures += 1
            time.sleep(2)
            continue

        if not result or result.get("status_code") != 0:
            status = result.get("status_code", "unknown") if result else "no response"
            print(f"[scraper] API returned status: {status}, retrying after delay...")
            consecutive_failures += 1
            time.sleep(3)
            continue

        consecutive_failures = 0

        comments = result.get("comments") or []
        if not comments:
            break

        for c in comments:
            cid = str(c.get("cid", c.get("id", "")))
            if cid in seen_ids:
                continue
            seen_ids.add(cid)

            parent_user = ""
            row = _parse_comment(c, reply_to_user=parent_user)
            rows.append(row)

            # Check if this comment has replies we should fetch
            reply_count = c.get("reply_comment_total", 0) or 0
            if reply_count > 0:
                username = row["username"]
                replies = _fetch_replies(page, video_id, cid, username, max_replies=reply_count)
                for r in replies:
                    rid = r.pop("_rid", "")
                    if rid and rid not in seen_ids:
                        seen_ids.add(rid)
                        rows.append(r)

        has_more = result.get("has_more", 0) == 1
        cursor = result.get("cursor", cursor + count)
        print(f"[scraper] Comments collected: {len(rows)} (cursor: {cursor})")

        # Small delay to avoid rate limiting
        time.sleep(1)

    return rows



def _fetch_replies(page, video_id: str, comment_id: str, parent_username: str, max_replies: int) -> list[dict]:
    """Fetch all replies to a specific comment."""
    replies = []
    cursor = 0
    count = 50

    while len(replies) < max_replies:
        api_url = (
            f"https://www.tiktok.com/api/comment/list/reply/"
            f"?aid=1988"
            f"&item_id={video_id}"
            f"&comment_id={comment_id}"
            f"&cursor={cursor}"
            f"&count={count}"
            f"&current_region=US"
        )

        try:
            result = page.evaluate(f"""
                async () => {{
                    const resp = await fetch("{api_url}", {{
                        credentials: 'include',
                    }});
                    return await resp.json();
                }}
            """)
        except Exception:
            break

        if not result or result.get("status_code") != 0:
            break

        comments = result.get("comments") or []
        if not comments:
            break

        for c in comments:
            cid = str(c.get("cid", c.get("id", "")))
            row = _parse_comment(c, reply_to_user=parent_username)
            row["_rid"] = cid
            replies.append(row)

        if result.get("has_more", 0) != 1:
            break
        cursor = result.get("cursor", cursor + count)
        time.sleep(0.5)

    return replies


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

    print(f"[scraper] Starting scrape for video {video_id}")
    print(f"[scraper] URL: {url}")

    rows = []

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

        # Visit the page to establish a valid session (cookies, tokens)
        print("[scraper] Loading page to establish session...")
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(3)

        # Dismiss any popups/overlays
        try:
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        # Try to extract comments from the page's embedded data first
        print("[scraper] Checking for embedded comment data...")
        embedded = _extract_embedded_data(page, video_id)
        if embedded:
            print(f"[scraper] Found {len(embedded)} comments in embedded data")
            rows.extend(embedded)

        # Fetch remaining comments via API
        api_rows = _fetch_comments_via_api(page, video_id, max_comments)
        if api_rows:
            # Merge, avoiding duplicates by (username, comment text, timestamp)
            existing = {(r["username"], r["comment"], r["timestamp"]) for r in rows}
            for r in api_rows:
                key = (r["username"], r["comment"], r["timestamp"])
                if key not in existing:
                    rows.append(r)
                    existing.add(key)

        browser.close()

    if not rows:
        print("[scraper] WARNING: No comments captured. The video may have comments disabled or TikTok blocked the request.")
        df = pd.DataFrame(columns=["username", "comment", "reply_to", "timestamp"])
        df.to_csv(csv_path, index=False)
        return csv_path

    df = pd.DataFrame(rows)
    df = df.sort_values("unix_timestamp").reset_index(drop=True)
    df = df[["username", "comment", "reply_to", "timestamp"]]
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"[scraper] Done! {len(df)} comments saved to {csv_path}")
    return csv_path


def _extract_embedded_data(page, video_id: str) -> list[dict]:
    """Try to extract comments from TikTok's embedded page data."""
    rows = []
    try:
        data = page.evaluate("""
            () => {
                // TikTok embeds data in __UNIVERSAL_DATA_FOR_REHYDRATION__
                const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                if (el) return JSON.parse(el.textContent);

                // Or in window object
                if (window.__UNIVERSAL_DATA_FOR_REHYDRATION__)
                    return window.__UNIVERSAL_DATA_FOR_REHYDRATION__;
                if (window.SIGI_STATE)
                    return window.SIGI_STATE;

                return null;
            }
        """)
        if not data:
            return rows

        # Navigate the nested structure to find comments
        # Structure varies, try common paths
        comments = None

        # Path 1: __DEFAULT_SCOPE__ -> webapp.video-detail
        default_scope = data.get("__DEFAULT_SCOPE__", {})
        video_detail = default_scope.get("webapp.video-detail", {})
        comments = video_detail.get("comments", [])

        if not comments:
            # Path 2: Look in comment module
            comment_item = default_scope.get("webapp.comment", {})
            comments = comment_item.get("comments", [])

        if not comments:
            # Path 3: SIGI_STATE style
            comment_module = data.get("CommentModule", {})
            comments = list(comment_module.get("comments", {}).values())

        for c in comments or []:
            rows.append(_parse_comment(c))

    except Exception as e:
        print(f"[scraper] Could not extract embedded data: {e}")

    return rows
