"""
CLI entry point for the TikTok comment scraper.

Usage:
    python src/main.py scrape "https://www.tiktok.com/@user/video/123"
    python src/main.py scrape --from-file urls.txt
    python src/main.py merge
"""

import argparse
import sys
from pathlib import Path

from scraper import scrape_video
from merger import merge_csvs


def cmd_scrape(args):
    urls = []

    if args.from_file:
        file_path = Path(args.from_file)
        if not file_path.exists():
            print(f"Error: File not found: {args.from_file}")
            sys.exit(1)
        urls = [
            line.strip()
            for line in file_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    elif args.url:
        urls = [args.url]
    else:
        print("Error: Provide a URL or --from-file")
        sys.exit(1)

    print(f"[main] Scraping {len(urls)} video(s)...")
    for i, url in enumerate(urls, 1):
        print(f"\n{'='*60}")
        print(f"[main] Video {i}/{len(urls)}: {url}")
        print(f"{'='*60}")
        try:
            scrape_video(
                url=url,
                output_dir=args.output,
                max_comments=args.max_comments,
                scroll_timeout=args.scroll_timeout,
            )
        except Exception as e:
            print(f"[main] ERROR scraping {url}: {e}")
            continue

    print(f"\n[main] All done. CSV files are in {args.output}/")


def cmd_merge(args):
    merge_csvs(output_dir=args.output, db_filename=args.db_name)


def main():
    parser = argparse.ArgumentParser(
        description="TikTok Comment Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output", default="output", help="Output directory (default: output)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- scrape ---
    sp_scrape = subparsers.add_parser("scrape", help="Scrape comments from a video")
    sp_scrape.add_argument("url", nargs="?", help="TikTok video URL")
    sp_scrape.add_argument(
        "--from-file",
        help="Text file with one TikTok URL per line",
    )
    sp_scrape.add_argument(
        "--max-comments",
        type=int,
        default=50000,
        help="Max comments to collect per video (default: 50000)",
    )
    sp_scrape.add_argument(
        "--scroll-timeout",
        type=int,
        default=5,
        help="Seconds to wait between scrolls (default: 5)",
    )
    sp_scrape.set_defaults(func=cmd_scrape)

    # --- merge ---
    sp_merge = subparsers.add_parser(
        "merge", help="Merge all comment CSVs into one database file"
    )
    sp_merge.add_argument(
        "--db-name",
        default="database.csv",
        help="Name of the merged database file (default: database.csv)",
    )
    sp_merge.set_defaults(func=cmd_merge)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
