#!/usr/bin/env python3
"""Trim podcast RSS feeds down to something Clay's RSS source can read.

Clay caps a source cell at 200kB. Podcast feeds blow past that because every
episode repeats the same sponsor boilerplate in both <description> and
<content:encoded>. For each show this keeps four fields per episode, drops the
repeated boilerplate, caps the description, and splits what is left across as
many files as it takes to stay under the ceiling.

Add a show by putting another entry in FEEDS.
"""

import html
import os
import re
import sys
from email.utils import format_datetime, formatdate
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from collections import Counter

import feedparser

# --- config -----------------------------------------------------------------

# One entry per show. "slug" names its output files: slug.xml, slug-2.xml ...
# Accounting Voices keeps the slug "feed" because that URL is already wired into
# Clay - renaming it would break the source.
FEEDS = [
    {"slug": "feed", "url": "https://feeds.captivate.fm/accounting-voices/"},
    {"slug": "cdg", "url": "https://feeds.megaphone.fm/CREUR4523040176"},
]

MAX_EPISODES = 300          # keep the N most recent episodes
MAX_DESCRIPTION_CHARS = 1200  # cap each description after HTML is stripped
MAX_BYTES = 180 * 1024      # per-file ceiling (Clay's cap is 200kB)

# Clay reads one file per RSS source, so an episode count that will not fit in
# MAX_BYTES is split across slug.xml, slug-2.xml, slug-3.xml ... Add each as its
# own source in Clay. Set to False to drop the oldest episodes instead.
SPLIT_INTO_PARTS = True

# Sponsor/preamble text repeats verbatim across most episodes and crowds out the
# real description. Any sentence appearing in this share of episodes is dropped,
# so the character budget is spent on content Clay can actually score.
STRIP_REPEATED_BOILERPLATE = True
# Shows rotate their sponsors, so an individual ad read appears in well under a
# tenth of episodes. 0.03 catches a sponsor that ran for a handful of weeks.
BOILERPLATE_MIN_SHARE = 0.03

# Rotating ad reads defeat frequency detection on their own, but they are nearly
# always introduced by a stock phrase and run to the end of the description.
# Everything from the first match is dropped. The guest intro comes first, so a
# match inside the opening SPONSOR_CUT_FLOOR characters is ignored as a false
# positive rather than beheading the episode.
SPONSOR_CUT_MARKERS = [
    r"This episode is brought to you by",
    r"Thank you to our Season Partners",
    r"Thanks? to our sponsors?\b",
    r"Sponsored by\b",
]
SPONSOR_CUT_FLOOR = 120

# ----------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_SPONSOR_RE = re.compile("|".join(SPONSOR_CUT_MARKERS), re.I)


def cut_sponsor_tail(text: str) -> str:
    match = _SPONSOR_RE.search(text)
    if match and match.start() > SPONSOR_CUT_FLOOR:
        return text[: match.start()].strip()
    return text


def sentences(text: str):
    return [s.strip() for s in _SENT_RE.split(text) if len(s.strip()) > 25]


def find_boilerplate(texts):
    """Sentences repeated across the feed - sponsor reads, series preambles."""
    if not STRIP_REPEATED_BOILERPLATE:
        return set()
    counts = Counter()
    for t in texts:
        for s in set(sentences(cut_sponsor_tail(t))):
            counts[s] += 1
    threshold = max(3, int(len(texts) * BOILERPLATE_MIN_SHARE))
    return {s for s, n in counts.items() if n >= threshold}


def drop_boilerplate(text: str, boilerplate) -> str:
    if not boilerplate:
        return text
    text = cut_sponsor_tail(text)
    kept = " ".join(s for s in sentences(text) if s not in boilerplate)
    # An episode whose whole description is boilerplate keeps its original text
    # rather than going out empty.
    return kept if len(kept) > 80 else text


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


def part_path(slug: str, index: int) -> str:
    """slug.xml, slug-2.xml, slug-3.xml ..."""
    return f"{slug}.xml" if index == 0 else f"{slug}-{index + 1}.xml"


def pack(episodes, channel):
    """Greedily fill one file up to MAX_BYTES; return (kept, remaining)."""
    lo, hi = 0, len(episodes)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(build_rss(*channel, episodes[:mid])) <= MAX_BYTES:
            lo = mid
        else:
            hi = mid - 1
    return episodes[:lo], episodes[lo:]


def run_feed(slug: str, url: str) -> int:
    print(f"\n{slug}: fetching {url}")
    parsed = feedparser.parse(url)

    if getattr(parsed, "bozo", 0) and not parsed.entries:
        print(f"ERROR: could not parse feed: {parsed.get('bozo_exception')}", file=sys.stderr)
        return 1
    if not parsed.entries:
        print("ERROR: feed contained no episodes", file=sys.stderr)
        return 1

    feed = parsed.feed
    channel_title = feed.get("title", "Podcast")
    channel_link = feed.get("link", url)
    channel_description = strip_html(feed.get("description", "") or channel_title, 500)
    channel = (channel_title, channel_link, channel_description)

    entries = sorted(parsed.entries, key=entry_timestamp, reverse=True)[:MAX_EPISODES]

    raw = [strip_html(e.get("summary", "") or e.get("subtitle", ""), 10 ** 9) for e in entries]
    boilerplate = find_boilerplate(raw)
    if boilerplate:
        print(f"  boilerplate sentences stripped: {len(boilerplate)}")

    episodes = []
    for entry, text in zip(entries, raw):
        body = drop_boilerplate(text, boilerplate)
        if len(body) > MAX_DESCRIPTION_CHARS:
            body = body[:MAX_DESCRIPTION_CHARS].rstrip()
            cut = body.rfind(" ")
            if cut > MAX_DESCRIPTION_CHARS * 0.8:
                body = body[:cut]
            body = body.rstrip(" ,;:-") + "\u2026"
        episodes.append(
            {
                "title": entry.get("title", "").strip(),
                "description": body,
                "link": entry.get("link", ""),
                "pubDate": rfc822(entry),
                "guid": entry.get("id", "") or entry.get("link", ""),
            }
        )

    remaining, written, dropped = episodes, [], 0
    while remaining:
        kept, remaining = pack(remaining, channel)
        if not kept:
            print("ERROR: a single episode exceeds the size ceiling", file=sys.stderr)
            return 1
        written.append(kept)
        if not SPLIT_INTO_PARTS:
            dropped = len(remaining)
            break

    for i, chunk in enumerate(written):
        payload = build_rss(*channel, chunk)
        path = part_path(slug, i)
        with open(path, "wb") as fh:
            fh.write(payload)
        span = f"{chunk[-1]['pubDate'][:16]} .. {chunk[0]['pubDate'][:16]}"
        print(f"  {path:<14} {len(chunk):>3} episodes  {len(payload) / 1024:>6.1f} kB   {span}")

    # Remove stale parts from a previous, larger run.
    i = len(written)
    while os.path.exists(part_path(slug, i)):
        os.remove(part_path(slug, i))
        print(f"  removed stale {part_path(slug, i)}")
        i += 1

    print(f"  {channel_title}: {len(parsed.entries)} available, {sum(len(c) for c in written)} kept"
          + (f", {dropped} dropped to fit" if dropped else ""))
    return 0


def main() -> int:
    failures = 0
    for spec in FEEDS:
        try:
            failures += run_feed(spec["slug"], spec["url"])
        except Exception as exc:  # one bad feed must not stop the others
            print(f"ERROR: {spec['slug']} failed: {exc}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
