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
    momentum: dict[int, float]        # window -> % return over window
    volatility_ann_pct: float         # annualized daily-return stdev
    rsi: float                        # 0..100
    dist_from_20d_high_pct: float     # how far below recent high (mean-reversion context)
    avg_dollar_volume_m: float        # liquidity sanity check, $ millions


def fetch_features(
    tickers: list[str],
    history_days: int,
    momentum_windows: list[int],
    vol_window: int,
    rsi_window: int,
) -> dict[str, TickerFeatures]:
    """Download daily bars for all tickers in one batch and compute features."""
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
            if len(df) < max(momentum_windows) + 5:
                print(f"[data] insufficient history for {t}, skipping")
                continue
            out[t] = _compute(t, df, momentum_windows, vol_window, rsi_window)
        except Exception as exc:
            print(f"[data] failed for {t}: {exc}")
    return out


def _compute(t: str, df: pd.DataFrame, mom_windows: list[int], vol_w: int, rsi_w: int) -> TickerFeatures:
    close = df["Close"]
    rets = close.pct_change().dropna()

    momentum = {w: float(close.iloc[-1] / close.iloc[-1 - w] - 1) * 100 for w in mom_windows}

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
    )


def _rsi(close: pd.Series, window: int) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
