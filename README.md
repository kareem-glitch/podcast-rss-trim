# Trimmed podcast RSS for Clay

Clay's RSS source caps a cell at 200kB. The Captivate feed for Accounting Voices is
~3.2MB because every episode repeats the same ~3,000-character sponsor boilerplate in
both `<description>` and `<content:encoded>`.

`trim_feed.py` rebuilds the feed as minimal RSS 2.0: per episode only `<title>`,
`<description>`, `<link>`, `<pubDate>` (plus a `<guid>`), HTML stripped, description
capped at 1200 characters, 60 most recent episodes, and the whole file guaranteed
under 180kB (oldest episodes are dropped if it would otherwise exceed).

Shows are listed in `FEEDS` at the top of the script, one entry per podcast.
Each gets up to **300 episodes with full 1200-char descriptions**, split across
as many files as the size ceiling requires.

Descriptions are never shortened to save space - Clay scores ICP fit from them.
Instead the script detects sentences repeated across the feed (the AdvanceTrack
sponsor read, series preambles - 37 of them here) and drops those, so the
character budget is spent on real content. Episodes that will still not fit in
one file overflow into numbered parts rather than being discarded.

## Public URLs for Clay

Add each as its own RSS source. Base:
`https://raw.githubusercontent.com/kareem-glitch/podcast-rss-trim/main/`

**Accounting Voices** - `feed.xml` (newest 115), `feed-2.xml` (115), `feed-3.xml` (oldest 70)

**Car Dealership Guy** - `cdg.xml` (newest 116), `cdg-2.xml` (119), `cdg-3.xml` (oldest 65)

Only the first file of each show (`feed.xml`, `cdg.xml`) ever receives new
episodes, so that is the one that needs a weekly schedule in Clay. The numbered
parts are back catalogue and can be pulled once.

The repo must be **public** for those URLs to work without a token.

## Adding another podcast

Add an entry to `FEEDS` at the top of `trim_feed.py`. The `slug` names its
output files; pick something short and URL-safe.

```python
FEEDS = [
    {"slug": "feed", "url": "https://feeds.captivate.fm/accounting-voices/"},
    {"slug": "cdg",  "url": "https://feeds.megaphone.fm/CREUR4523040176"},
]
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
