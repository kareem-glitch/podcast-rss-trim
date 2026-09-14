#!/usr/bin/env python3
"""Trim a podcast RSS feed down to something Clay's RSS source can read.

Clay caps a source cell at 200kB. Feeds like Captivate's blow past that because
every episode repeats the same sponsor boilerplate in both <description> and
<content:encoded>. This script keeps four fields per episode, strips the HTML,
caps the description, and drops the oldest episodes until the file is under the
size ceiling.

Point FEED_URL at a different podcast to reuse it.
"""

import html
import re
import sys
from email.utils import format_datetime, formatdate
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import feedparser

# --- config -----------------------------------------------------------------

FEED_URL = "https://feeds.captivate.fm/accounting-voices/"
OUTPUT_PATH = "feed.xml"

MAX_EPISODES = 60           # keep the N most recent episodes
MAX_DESCRIPTION_CHARS = 1200  # cap each description after HTML is stripped
MAX_BYTES = 180 * 1024      # hard ceiling; oldest episodes are dropped to fit

# ----------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(raw: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    """Turn an HTML description into a single line of plain text, capped."""
    if not raw:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", " ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip()
        # don't cut mid-word if we can avoid it
        cut = text.rfind(" ")
        if cut > limit * 0.8:
            text = text[:cut]
        text = text.rstrip(" ,;:-") + "…"
    return text


def entry_timestamp(entry) -> float:
    """Sortable timestamp for an entry; 0 when the feed gives us nothing."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc).timestamp()
    return 0.0


def rfc822(entry) -> str:
    """RFC-822 pubDate, preferring the feed's own string when it has one."""
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            return raw
    ts = entry_timestamp(entry)
    if ts:
        return formatdate(ts, usegmt=True)
    return ""


def build_rss(channel_title, channel_link, channel_description, episodes) -> bytes:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = channel_link
    ET.SubElement(channel, "description").text = channel_description
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc), usegmt=True
    )

    for ep in episodes:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = ep["title"]
        ET.SubElement(item, "description").text = ep["description"]
        if ep["link"]:
            ET.SubElement(item, "link").text = ep["link"]
        if ep["pubDate"]:
            ET.SubElement(item, "pubDate").text = ep["pubDate"]
        if ep["guid"]:
            guid = ET.SubElement(item, "guid", {"isPermaLink": "false"})
            guid.text = ep["guid"]

    ET.indent(rss, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        rss, encoding="utf-8", xml_declaration=False
    )


def main() -> int:
    print(f"Fetching {FEED_URL}")
    parsed = feedparser.parse(FEED_URL)

    if getattr(parsed, "bozo", 0) and not parsed.entries:
        print(f"ERROR: could not parse feed: {parsed.get('bozo_exception')}", file=sys.stderr)
        return 1
    if not parsed.entries:
        print("ERROR: feed contained no episodes", file=sys.stderr)
        return 1

    feed = parsed.feed
    channel_title = feed.get("title", "Podcast")
    channel_link = feed.get("link", FEED_URL)
    channel_description = strip_html(feed.get("description", "") or channel_title, 500)

    entries = sorted(parsed.entries, key=entry_timestamp, reverse=True)[:MAX_EPISODES]

    episodes = []
    for entry in entries:
        raw_desc = entry.get("summary", "") or entry.get("subtitle", "")
        episodes.append(
            {
                "title": entry.get("title", "").strip(),
                "description": strip_html(raw_desc),
                "link": entry.get("link", ""),
                "pubDate": rfc822(entry),
                "guid": entry.get("id", "") or entry.get("link", ""),
            }
        )

    dropped = 0
    while episodes:
        payload = build_rss(channel_title, channel_link, channel_description, episodes)
        if len(payload) <= MAX_BYTES:
            break
        episodes.pop()  # oldest first, since the list is newest-first
        dropped += 1
    else:
        print("ERROR: channel metadata alone exceeds the size ceiling", file=sys.stderr)
        return 1

    with open(OUTPUT_PATH, "wb") as fh:
        fh.write(payload)

    size_kb = len(payload) / 1024
    print(f"Source episodes:  {len(parsed.entries)}")
    print(f"Kept:             {len(episodes)}")
    if dropped:
        print(f"Dropped to fit:   {dropped} (oldest)")
    print(f"Wrote {OUTPUT_PATH}: {size_kb:.1f} kB (ceiling {MAX_BYTES / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
