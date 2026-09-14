# Trimmed podcast RSS for Clay

Clay's RSS source caps a cell at 200kB. The Captivate feed for Accounting Voices is
~3.2MB because every episode repeats the same ~3,000-character sponsor boilerplate in
both `<description>` and `<content:encoded>`.

`trim_feed.py` rebuilds the feed as minimal RSS 2.0: per episode only `<title>`,
`<description>`, `<link>`, `<pubDate>` (plus a `<guid>`), HTML stripped, description
capped at 1200 characters, 60 most recent episodes, and the whole file guaranteed
under 180kB (oldest episodes are dropped if it would otherwise exceed).

Current output: **all 300 episodes, full 1200-char descriptions, split across 3 files.**

Descriptions are never shortened to save space - Clay scores ICP fit from them.
Instead the script detects sentences repeated across the feed (the AdvanceTrack
sponsor read, series preambles - 37 of them here) and drops those, so the
character budget is spent on real content. Episodes that will still not fit in
one file overflow into numbered parts rather than being discarded.

## Public URLs for Clay

Add each as its own RSS source:

```
https://raw.githubusercontent.com/kareem-glitch/podcast-rss-trim/main/feed.xml     newest 115
https://raw.githubusercontent.com/kareem-glitch/podcast-rss-trim/main/feed-2.xml   next 115
https://raw.githubusercontent.com/kareem-glitch/podcast-rss-trim/main/feed-3.xml   oldest 70
```

The repo must be **public** for those URLs to work without a token.

## Pointing it at another podcast

Edit the constants at the top of `trim_feed.py`:

```python
FEED_URL = "https://feeds.captivate.fm/accounting-voices/"
OUTPUT_PATH = "feed.xml"
MAX_EPISODES = 300
MAX_DESCRIPTION_CHARS = 1200
MAX_BYTES = 180 * 1024        # per file
SPLIT_INTO_PARTS = True       # False = drop oldest instead of overflowing
STRIP_REPEATED_BOILERPLATE = True
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
