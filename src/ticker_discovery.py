"""Use Claude's live web search to surface tickers actively in today's news,
beyond the fixed watchlist in config.yaml — including recent IPOs.

This only ever proposes candidate ticker symbols + a one-line reason. It does
not judge, score, or rank anything: candidates still have to (a) resolve to
real, tradeable price data and (b) clear the same liquidity floor and news
materiality bar as every other ticker before they can appear as a pick. A
noisy or wrong web search just means fewer candidates survive — it can't
force a bad pick through.
"""
from __future__ import annotations

import json
import os

import anthropic

DISCOVERY_PROMPT_TEMPLATE = """Search the web for {asset_label} that are actively in financial news \
today and could plausibly see a noticeable price move today, in either direction — for example due to \
earnings, upgrades/downgrades, M&A rumors, unusual volume, or being a recent IPO. Run a few distinct \
searches to cover different angles (e.g. general market movers, and recent IPOs specifically), not just \
one search.

When you're done searching, respond with ONLY a JSON array (no prose, no markdown fences) of up to 12 \
objects:
{{
  "ticker": "the exact trading symbol as it would appear on Yahoo Finance, e.g. AAPL, SAP.DE, or BTC-USD",
  "why": "one short sentence on why it's in the news right now"
}}

Only include tickers you are reasonably confident actually exist and trade publicly — if you're not
sure a symbol is right, leave it out rather than guess. If nothing newsworthy turns up, return []."""


def discover_tickers(model: str, asset_label: str, max_searches: int = 4) -> list[dict]:
    """Returns up to ~12 {ticker, why} candidates, or [] if search is
    unavailable/fails/finds nothing. Never raises — a discovery failure
    should never take down the rest of the run."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}],
            messages=[{"role": "user", "content": DISCOVERY_PROMPT_TEMPLATE.format(asset_label=asset_label)}],
        )
    except Exception as exc:
        print(f"[discovery] web search failed, skipping: {exc}")
        return []

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict) and d.get("ticker")]
    except json.JSONDecodeError as exc:
        print(f"[discovery] JSON parse failed: {exc}\nRaw head: {cleaned[:300]}")
    return []
