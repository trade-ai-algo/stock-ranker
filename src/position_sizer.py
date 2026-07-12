"""Illustrative euro-stake sizing for a hypothetical capital pool.

Applies a fixed, transparent confidence -> stake-% tier to each pick (the
confidence label already fuses the LLM's stated confidence with signal
agreement and volatility — see ranker.py), scales every stake down pro-rata
if a day's picks would deploy more than a set ceiling of the pool, then
reports what the LLM's own speculative close-move estimate — and the name's
*actual* historical daily volatility — would imply in euros.

This is a worked example, not a trading system: the sizing rule is fixed
math applied to numbers the pipeline already produces, it doesn't feed back
into ranking, and none of it is investment advice.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .ranker import RankedPick


@dataclass
class StakeExample:
    ticker: str
    stake_eur: float
    stake_pct: float
    est_close_pnl_eur: float
    typical_daily_swing_eur: float


def size_book(
    picks: list[RankedPick],
    capital_eur: float,
    stake_pct_by_confidence: dict[str, float],
    max_total_deployed_pct: float,
) -> tuple[list[StakeExample], dict]:
    raw_pct = [stake_pct_by_confidence.get(p.confidence_label, 0.0) for p in picks]
    raw_total_pct = sum(raw_pct)
    scale = 1.0
    if raw_total_pct > max_total_deployed_pct and raw_total_pct > 0:
        scale = max_total_deployed_pct / raw_total_pct

    examples: list[StakeExample] = []
    total_stake = 0.0
    total_pnl = 0.0
    sq_swing_sum = 0.0

    for p, pct in zip(picks, raw_pct):
        stake_pct = pct * scale
        stake_eur = capital_eur * stake_pct
        est_close_pnl_eur = stake_eur * (p.est_close_move_pct / 100)
        vol_ann_pct = p.components.get("vol_ann_pct", 0.0)
        daily_vol_pct = vol_ann_pct / math.sqrt(252)
        typical_daily_swing_eur = stake_eur * (daily_vol_pct / 100)

        examples.append(
            StakeExample(
                ticker=p.ticker,
                stake_eur=round(stake_eur, 2),
                stake_pct=round(stake_pct * 100, 1),
                est_close_pnl_eur=round(est_close_pnl_eur, 2),
                typical_daily_swing_eur=round(typical_daily_swing_eur, 2),
            )
        )
        total_stake += stake_eur
        total_pnl += est_close_pnl_eur
        sq_swing_sum += typical_daily_swing_eur**2

    summary = {
        "total_stake_eur": round(total_stake, 2),
        "total_stake_pct": round((total_stake / capital_eur) * 100, 1) if capital_eur else 0.0,
        "cash_left_eur": round(capital_eur - total_stake, 2),
        "est_close_pnl_eur": round(total_pnl, 2),
        # Combined 1-std-dev swing assuming roughly independent picks — a portfolio-level
        # estimate, not a guarantee; correlated names (e.g. two tech stocks) will move together
        # more than this implies.
        "typical_daily_swing_eur": round(math.sqrt(sq_swing_sum), 2),
        "scaled_down": scale < 1.0,
    }
    return examples, summary
