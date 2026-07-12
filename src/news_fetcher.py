"""Fetch recent financial news headlines from RSS feeds."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser


@dataclass
class Headline:
    title: str
    summary: str
    source: str
    published: datetime
    link: str


def fetch_headlines(rss_feeds: list[str], lookback_hours: int, max_headlines: int) -> list[Headline]:
    """Pull headlines from all feeds, keep only recent ones, dedupe, cap count."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    items: list[Headline] = []

    for url in rss_feeds:
        try:
            feed = feedparser.parse(url)
        except Exception as exc:  # network hiccups shouldn't kill the run
            print(f"[news] failed to fetch {url}: {exc}")
            continue

        source = feed.feed.get("title", url)
        for entry in feed.entries:
            published = _parse_time(entry)
            if published is None or published < cutoff:
                continue
            items.append(
                Headline(
                    title=entry.get("title", "").strip(),
                    summary=_clean(entry.get("summary", ""))[:400],
                    source=source,
                    published=published,
                    link=entry.get("link", ""),
                )
            )

    # Dedupe by lowercase title, newest first
    seen: set[str] = set()
    unique: list[Headline] = []
    for h in sorted(items, key=lambda x: x.published, reverse=True):
        key = h.title.lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(h)

    return unique[:max_headlines]


def _parse_time(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = entry.get(attr)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def _clean(html: str) -> str:
    """Crude HTML strip — good enough for RSS summaries."""
    import re

    return re.sub(r"<[^>]+>", " ", html).replace("\xa0", " ").strip()
