"""Fuse LLM news scores with quantitative features into a final ranking.

Deterministic and auditable: given the same inputs, same output.
The LLM only supplies news_score/confidence/estimate components; everything
else — including position in the ranking — is math.
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
    confidence_score: float
    confidence_label: str
    est_open_move_pct: float
    est_close_move_pct: float
    components: dict = field(default_factory=dict)


def rank_by_group(
    llm_scores: list[dict],
    features: dict[str, TickerFeatures],
    ticker_group: dict[str, str],
    weights: dict[str, float],
    top_n: int,
    allow_no_pick: bool,
    min_score: float = 0.10,
) -> dict[str, list[RankedPick]]:
    """Score every eligible ticker once, then rank and cap independently per
    group (e.g. per market) so each group gets its own top_n suggestions
    instead of one group crowding out another in a single global list.
    Every group key present in `ticker_group` is guaranteed a (possibly
    empty) entry in the result."""
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

        # Confidence: fuses the LLM's own stated confidence with two deterministic
        # checks — do news and momentum actually agree in direction, and is the name
        # calm enough that a move means something. Informational only; never affects
        # total_score or ranking order (the LLM still never ranks).
        llm_confidence = float(np.clip(news.get("confidence", 0.5), 0, 1))
        agree = (
            1.0
            if news_score == 0 or momentum_score == 0
            else float(np.sign(news_score) == np.sign(momentum_score))
        )
        calm = float(np.clip(1 - f.volatility_ann_pct / 60.0, 0, 1))
        confidence_score = float(np.clip(0.5 * llm_confidence + 0.3 * agree + 0.2 * calm, 0, 1))
        confidence_label = "High" if confidence_score >= 0.7 else "Medium" if confidence_score >= 0.4 else "Low"

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
                confidence_score=round(confidence_score, 3),
                confidence_label=confidence_label,
                est_open_move_pct=round(float(np.clip(news.get("est_open_move_pct", 0.0), -10, 10)), 2),
                est_close_move_pct=round(float(np.clip(news.get("est_close_move_pct", 0.0), -10, 10)), 2),
                components={
                    "rsi": f.rsi,
                    "mom20d_pct": mom20,
                    "overnight_gap_pct": f.overnight_gap_pct,
                    "vol_ann_pct": f.volatility_ann_pct,
                    "adv_musd": f.avg_dollar_volume_m,
                },
            )
        )

    grouped: dict[str, list[RankedPick]] = {g: [] for g in dict.fromkeys(ticker_group.values())}
    for p in picks:
        grouped.setdefault(ticker_group.get(p.ticker, "other"), []).append(p)

    for g, group_picks in grouped.items():
        group_picks.sort(key=lambda p: p.total_score, reverse=True)
        if allow_no_pick:
            # Only surface picks with a meaningfully positive fused score.
            group_picks = [p for p in group_picks if p.total_score > min_score]
        grouped[g] = group_picks[:top_n]

    return grouped
