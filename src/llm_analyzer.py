"""Send headlines + quant context to Claude, get structured news scores back.

The LLM's job is narrow and auditable: map news to tickers, judge sentiment
and MATERIALITY, and say whether the move is likely already priced in.
It does NOT produce the final ranking — the deterministic ranker does.
"""
from __future__ import annotations

import json
import os

import anthropic

from .market_data import TickerFeatures
from .news_fetcher import Headline

SYSTEM_PROMPT = """You are a sell-side news analyst. You will receive (1) recent \
financial headlines and (2) per-ticker quantitative context including the \
overnight gap. For each ticker in the universe that is materially affected by \
the news, output a JSON object. Respond with ONLY a JSON array, no prose, no \
markdown fences.

Schema per element:
{
  "ticker": "AAPL",
  "sentiment": -1.0 to 1.0,          // direction of the news for the stock
  "materiality": 0.0 to 1.0,         // earnings/guidance/M&A/regulatory high; fluff PR low
  "priced_in": 0.0 to 1.0,           // 1.0 = overnight gap already reflects the news fully
  "catalyst": "earnings_beat|guidance|mna|regulatory|macro|analyst|product|other",
  "rationale": "one sentence, max 25 words",
  "risk": "one sentence on the main way this thesis fails, max 20 words"
}

Rules:
- Only include tickers with materiality >= 0.3. Omitting all tickers is a valid answer: return [].
- Judge priced_in using the overnight gap provided: big gap in the news direction = mostly priced in.
- Never invent news. If headlines don't clearly concern a ticker, leave it out.
- Be conservative: generic market commentary is materiality ~0.1 and should be excluded."""


def analyze_news(
    headlines: list[Headline],
    features: dict[str, TickerFeatures],
    model: str,
    max_tokens: int,
) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY environment variable.")

    client = anthropic.Anthropic(api_key=api_key)

    news_block = "\n".join(
        f"- [{h.source} | {h.published:%Y-%m-%d %H:%M}Z] {h.title} :: {h.summary}"
        for h in headlines
    )
    quant_block = "\n".join(
        f"- {f.ticker}: close={f.last_close}, overnight_gap={f.overnight_gap_pct}%, "
        f"mom20d={f.momentum.get(20, 0)}%, RSI={f.rsi}, vol={f.volatility_ann_pct}%"
        for f in features.values()
    )
    user_msg = (
        f"UNIVERSE (only these tickers are eligible):\n{quant_block}\n\n"
        f"HEADLINES (last ~20h):\n{news_block}\n\n"
        "Return the JSON array now."
    )

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return _parse_json_array(text)


def _parse_json_array(text: str) -> list[dict]:
    """Robustly parse; strip accidental code fences; fail soft to []."""
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict) and "ticker" in d]
    except json.JSONDecodeError as exc:
        print(f"[llm] JSON parse failed: {exc}\nRaw head: {cleaned[:300]}")
    return []
