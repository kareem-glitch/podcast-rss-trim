# Trimmed podcast RSS for Clay

Clay's RSS source caps a cell at 200kB. The Captivate feed for Accounting Voices is
~3.2MB because every episode repeats the same ~3,000-character sponsor boilerplate in
both `<description>` and `<content:encoded>`.

`trim_feed.py` rebuilds the feed as minimal RSS 2.0: per episode only `<title>`,
`<description>`, `<link>`, `<pubDate>` (plus a `<guid>`), HTML stripped, description
capped at 1200 characters, 60 most recent episodes, and the whole file guaranteed
under 180kB (oldest episodes are dropped if it would otherwise exceed).

Current output: **60 episodes, ~94kB**.

## Public URL for Clay

```
https://raw.githubusercontent.com/<owner>/<repo>/main/feed.xml
```

The repo must be **public** for that URL to work without a token.

## Pointing it at another podcast

Edit the constants at the top of `trim_feed.py`:

```python
FEED_URL = "https://feeds.captivate.fm/accounting-voices/"
OUTPUT_PATH = "feed.xml"
MAX_EPISODES = 60
MAX_DESCRIPTION_CHARS = 1200
MAX_BYTES = 180 * 1024
```

## Run locally

```bash
pip install -r requirements.txt
python trim_feed.py
```

## Automation

`.github/workflows/update-feed.yml` runs every Monday at 06:15 UTC (and on demand via
**Actions → Update trimmed feed → Run workflow**), rebuilds `feed.xml`, and commits it
only when the content changed.
