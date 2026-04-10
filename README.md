# TikTok Comment Scraper

Scrapes comments + replies from TikTok videos into CSVs. Merge them into one big database file.

## You need

- [Docker](https://www.docker.com/products/docker-desktop/)

## Usage

```bash
# build (once)
docker compose build

# scrape a video
docker compose run --rm scraper scrape "https://www.tiktok.com/@user/video/7123456789"

# scrape multiple from a file (one url per line)
docker compose run --rm scraper scrape --from-file /app/output/urls.txt

# merge all csvs into output/database.csv
docker compose run --rm scraper merge
```

CSVs end up in `output/`.

## CSV columns

| Column | What it is |
|---|---|
| `username` | commenter's username |
| `comment` | the comment text |
| `reply_to` | who they replied to (empty if top-level) |
| `timestamp` | human-readable, UTC |
| `video_id` | only in merged database.csv |

## Notes

- TikTok might rate-limit you. If you get 0 comments, wait a bit and try again.
- Replies get fetched automatically.
- Timestamps are UTC.
