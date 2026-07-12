"""Historical price data and quantitative features per ticker.

Uses yfinance (free, delayed — fine for daily ranking, NOT for execution).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class TickerFeatures:
    ticker: str
    last_close: float
    overnight_gap_pct: float          # today's open vs yesterday's close (news priced in?)
    momentum: dict[int, float]        # window -> % return over window (only windows that fit the history)
    volatility_ann_pct: float         # annualized daily-return stdev
    rsi: float                        # 0..100
    dist_from_20d_high_pct: float     # how far below recent high (mean-reversion context)
    avg_dollar_volume_m: float        # liquidity sanity check, $ millions
    is_ipo: bool                      # listed more recently than ipo_lookback_days


def fetch_features(
    tickers: list[str],
    history_days: int,
    momentum_windows: list[int],
    vol_window: int,
    rsi_window: int,
    min_history_days: int | None = None,
    ipo_lookback_days: int = 90,
) -> dict[str, TickerFeatures]:
    """Download daily bars for all tickers in one batch and compute features.

    A ticker only needs `min_history_days` of real trading history to be
    included at all (default: enough for the longest momentum window, the
    old strict behavior). Callers that also want to surface recent IPOs
    should pass a much lower `min_history_days` (e.g. ~25, enough for a
    meaningful volatility/RSI read) — momentum windows longer than the
    available history are simply omitted rather than skipping the ticker.
    """
    min_days = min_history_days if min_history_days is not None else max(momentum_windows) + 5

    data = yf.download(
        tickers,
        period=f"{history_days}d",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    out: dict[str, TickerFeatures] = {}
    for t in tickers:
        try:
            df = data[t].dropna() if len(tickers) > 1 else data.dropna()
            if len(df) < min_days:
                print(f"[data] insufficient history for {t}, skipping")
                continue
            out[t] = _compute(t, df, momentum_windows, vol_window, rsi_window, ipo_lookback_days)
        except Exception as exc:
            print(f"[data] failed for {t}: {exc}")
    return out


def _compute(
    t: str, df: pd.DataFrame, mom_windows: list[int], vol_w: int, rsi_w: int, ipo_lookback_days: int
) -> TickerFeatures:
    close = df["Close"]
    rets = close.pct_change().dropna()

    # Only windows that fit within the available history — short-history names
    # (e.g. recent IPOs) just get fewer momentum points instead of being skipped.
    momentum = {w: float(close.iloc[-1] / close.iloc[-1 - w] - 1) * 100 for w in mom_windows if len(close) > w}

    gap = float(df["Open"].iloc[-1] / close.iloc[-2] - 1) * 100

    vol = float(rets.iloc[-vol_w:].std() * np.sqrt(252)) * 100

    rsi = _rsi(close, rsi_w)

    high20 = float(close.iloc[-20:].max())
    dist_high = float(close.iloc[-1] / high20 - 1) * 100

    adv = float((df["Close"] * df["Volume"]).iloc[-20:].mean() / 1e6)

    return TickerFeatures(
        ticker=t,
        last_close=round(float(close.iloc[-1]), 2),
        overnight_gap_pct=round(gap, 2),
        momentum={k: round(v, 2) for k, v in momentum.items()},
        volatility_ann_pct=round(vol, 1),
        rsi=round(rsi, 1),
        dist_from_20d_high_pct=round(dist_high, 2),
        avg_dollar_volume_m=round(adv, 1),
        is_ipo=len(df) < ipo_lookback_days,
    )


def _rsi(close: pd.Series, window: int) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
