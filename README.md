# TikTok Comment Scraper

Scrapes comments and replies from TikTok videos into CSV files. Each video is scraped independently, and a merge function combines them into one database file.

Built with Python, Playwright (headless Chromium), and pandas. Runs locally in Docker.

## Data Collected

| Column      | Description                                          |
|-------------|------------------------------------------------------|
| `username`  | Commenter's TikTok username                          |
| `comment`   | The comment text                                     |
| `reply_to`  | Username of the parent comment (empty if top-level)  |
| `timestamp` | Human-readable timestamp (`2026-04-09 14:30:00 UTC`) |
| `video_id`  | Video ID (only in merged database)                   |

## Quick Start (Docker)

```bash
# Build the image
docker compose build

# Scrape a single video
docker compose run scraper scrape "https://www.tiktok.com/@user/video/7123456789"

# Scrape multiple videos from a file
docker compose run scraper scrape --from-file /app/output/urls.txt

# Merge all scraped CSVs into one database
docker compose run scraper merge
```

CSV files appear in the `output/` folder on your host machine.

## Quick Start (Local)

Requires Python 3.11+.

```bash
pip install -r requirements.txt
playwright install chromium

# Scrape
python src/main.py scrape "https://www.tiktok.com/@user/video/7123456789"

# Merge
python src/main.py merge
```

## CLI Reference

### `scrape`

```
python src/main.py scrape [URL] [OPTIONS]

Arguments:
  URL                       TikTok video URL

Options:
  --from-file FILE          Text file with one URL per line (lines starting with # are ignored)
  --max-comments N          Max comments per video (default: 50000)
  --scroll-timeout SECONDS  Wait time between scrolls (default: 5)
  --output DIR              Output directory (default: output)
```

### `merge`

```
python src/main.py merge [OPTIONS]

Options:
  --db-name FILENAME   Name of merged file (default: database.csv)
  --output DIR         Directory containing the CSVs (default: output)
```

## Output Files

```
output/
  comments_7123456789.csv   # Individual video
  comments_7987654321.csv   # Individual video
  database.csv              # Merged database (after running merge)
```

## URL File Format

Create a text file with one TikTok URL per line:

```
# my-videos.txt
https://www.tiktok.com/@user1/video/7123456789
https://www.tiktok.com/@user2/video/7987654321
https://www.tiktok.com/@user3/video/7111222333
```

## Notes

- TikTok may rate-limit or block requests. If a scrape returns 0 comments, try again after a few minutes or increase `--scroll-timeout`.
- The scraper intercepts TikTok's internal API responses, so it gets structured data directly rather than parsing HTML.
- Handles large comment sections (10,000+) by scrolling automatically and loading replies.
- All timestamps are in UTC.
