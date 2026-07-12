"""Fuse LLM news scores with quantitative features into a final ranking.

Deterministic and auditable: given the same inputs, same output.
The LLM only supplies news_score components; everything else is math.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .market_data import TickerFeatures


@dataclass
class RankedPick:
    ticker: str
    total_score: float
    news_score: float
    momentum_score: float
    mean_reversion_score: float
    gap_penalty: float
    catalyst: str
    rationale: str
    risk: str
    last_close: float
    components: dict = field(default_factory=dict)


def rank(
    llm_scores: list[dict],
    features: dict[str, TickerFeatures],
    weights: dict[str, float],
    top_n: int,
    allow_no_pick: bool,
) -> list[RankedPick]:
    news_by_ticker = {d["ticker"]: d for d in llm_scores if d.get("ticker") in features}

    picks: list[RankedPick] = []
    for ticker, news in news_by_ticker.items():
        f = features[ticker]

        # News: sentiment direction scaled by materiality → [-1, 1]
        news_score = float(np.clip(news.get("sentiment", 0), -1, 1)) * float(
            np.clip(news.get("materiality", 0), 0, 1)
        )

        # Momentum: blend of 20d and 60d returns, squashed to [-1, 1]
        mom20 = f.momentum.get(20, 0.0)
        mom60 = f.momentum.get(60, 0.0)
        momentum_score = float(np.tanh((0.6 * mom20 + 0.4 * mom60) / 10.0))

        # Mean reversion: penalize chasing overbought names (RSI > 70),
        # small bonus for oversold names with positive news.
        if f.rsi >= 70:
            mr_score = -(f.rsi - 70) / 30.0
        elif f.rsi <= 30 and news_score > 0:
            mr_score = (30 - f.rsi) / 30.0
        else:
            mr_score = 0.0
        mr_score = float(np.clip(mr_score, -1, 1))

        # Priced-in penalty: LLM's judgment, reinforced by the measured gap.
        priced_in = float(np.clip(news.get("priced_in", 0.5), 0, 1))
        gap_in_news_direction = f.overnight_gap_pct * np.sign(news_score or 1)
        gap_reinforce = float(np.clip(gap_in_news_direction / 3.0, 0, 1))  # 3% gap = fully priced
        gap_penalty = -max(priced_in, gap_reinforce)  # always <= 0

        total = (
            weights["news_score"] * news_score
            + weights["momentum"] * momentum_score
            + weights["mean_reversion"] * mr_score
            + weights["gap_penalty"] * gap_penalty
        )

        picks.append(
            RankedPick(
                ticker=ticker,
                total_score=round(float(total), 4),
                news_score=round(news_score, 3),
                momentum_score=round(momentum_score, 3),
                mean_reversion_score=round(mr_score, 3),
                gap_penalty=round(gap_penalty, 3),
                catalyst=news.get("catalyst", "other"),
                rationale=news.get("rationale", ""),
                risk=news.get("risk", ""),
                last_close=f.last_close,
                components={
                    "rsi": f.rsi,
                    "mom20d_pct": mom20,
                    "overnight_gap_pct": f.overnight_gap_pct,
                    "vol_ann_pct": f.volatility_ann_pct,
                    "adv_musd": f.avg_dollar_volume_m,
                },
            )
        )

    picks.sort(key=lambda p: p.total_score, reverse=True)

    if allow_no_pick:
        # Only surface picks with a meaningfully positive fused score.
        picks = [p for p in picks if p.total_score > 0.10]

    return picks[:top_n]
