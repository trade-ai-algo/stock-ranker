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

SYSTEM_PROMPT_TEMPLATE = """You are a sell-side analyst covering {asset_label}. You will receive (1) \
recent headlines and (2) per-ticker quantitative context including the overnight gap. For each ticker \
in the universe that is materially affected by the news, output a JSON object. Respond with ONLY a \
JSON array, no prose, no markdown fences.

Schema per element:
{{
  "ticker": "AAPL",
  "sentiment": -1.0 to 1.0,          // direction of the news for the asset
  "materiality": 0.0 to 1.0,         // major fundamental catalysts (see list below) high; fluff/generic commentary low
  "priced_in": 0.0 to 1.0,           // 1.0 = overnight gap already reflects the news fully
  "confidence": 0.0 to 1.0,          // how sure you are of this whole read (news + numbers together)
  "est_open_move_pct": -10.0 to 10.0,  // your speculative point-estimate gap at next session open vs last close
  "est_close_move_pct": -10.0 to 10.0, // your speculative point-estimate cumulative move by next session close
  "catalyst": "{catalyst_options}",
  "rationale": "one sentence, max 25 words",
  "risk": "one sentence on the main way this thesis fails, max 20 words"
}}

Rules:
- "ticker" must be copied EXACTLY as it appears in the UNIVERSE block below, including any
  exchange/quote suffix (e.g. "TTE.PA", not "TTE"; "BTC-USD", not "BTC"). A ticker that doesn't
  exactly match the universe is silently dropped, wasting a real signal.
- Only include tickers with materiality >= 0.3. Omitting all tickers is a valid answer: return [].
- Judge priced_in using the overnight gap provided: big gap in the news direction = mostly priced in.
- est_open_move_pct / est_close_move_pct are your own speculative guesses, grounded in the momentum/RSI/
  volatility context given plus the news — not a prediction service, not investment advice. Use 0 if you
  have no informed view beyond noise.
- confidence should be low (<0.3) when headlines are thin, stale, or contradictory, and high (>0.7) only
  when materiality and the quant context clearly agree.
- Never invent news. If headlines don't clearly concern a ticker, leave it out.
- Be conservative: generic commentary is materiality ~0.1 and should be excluded."""


def analyze_news(
    headlines: list[Headline],
    features: dict[str, TickerFeatures],
    model: str,
    max_tokens: int,
    asset_label: str = "equities and ETFs",
    catalyst_options: str = "earnings_beat|guidance|mna|regulatory|macro|analyst|product|other",
) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY environment variable.")

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(asset_label=asset_label, catalyst_options=catalyst_options)

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
        system=system_prompt,
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
