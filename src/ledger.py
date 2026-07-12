"""Suggestion ledger: log every pick, evaluate it later vs the benchmark.

This is the honest-scorekeeping half of the system. After a few months of
rows, `summary()` tells you whether the picks actually beat the benchmark —
which is the only question that matters.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import yfinance as yf

SCHEMA = """
CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    rank INTEGER NOT NULL,
    total_score REAL,
    price_at_pick REAL,
    catalyst TEXT,
    rationale TEXT,
    risk TEXT
);
CREATE TABLE IF NOT EXISTS evaluations (
    pick_id INTEGER NOT NULL REFERENCES picks(id),
    horizon_days INTEGER NOT NULL,
    pick_return_pct REAL,
    benchmark_return_pct REAL,
    excess_return_pct REAL,
    evaluated_at TEXT,
    PRIMARY KEY (pick_id, horizon_days)
);
"""


class Ledger:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ── writing picks ────────────────────────────────────────────────
    def log_picks(self, run_date: date, picks) -> None:
        for i, p in enumerate(picks, start=1):
            self.conn.execute(
                "INSERT INTO picks (run_date, ticker, rank, total_score, "
                "price_at_pick, catalyst, rationale, risk) VALUES (?,?,?,?,?,?,?,?)",
                (
                    run_date.isoformat(),
                    p.ticker,
                    i,
                    p.total_score,
                    p.last_close,
                    p.catalyst,
                    p.rationale,
                    p.risk,
                ),
            )
        self.conn.commit()

    # ── evaluating past picks ────────────────────────────────────────
    def evaluate_due(self, horizons: list[int], benchmark: str) -> int:
        """Evaluate picks whose horizon has elapsed and lack an evaluation."""
        today = date.today()
        rows = self.conn.execute(
            "SELECT id, run_date, ticker, price_at_pick FROM picks"
        ).fetchall()

        n_evaluated = 0
        for pick_id, run_date_s, ticker, price_at_pick in rows:
            run_d = date.fromisoformat(run_date_s)
            for h in horizons:
                if (today - run_d).days < h + 1:
                    continue
                exists = self.conn.execute(
                    "SELECT 1 FROM evaluations WHERE pick_id=? AND horizon_days=?",
                    (pick_id, h),
                ).fetchone()
                if exists:
                    continue

                pick_ret = _return_over(ticker, run_d, h)
                bench_ret = _return_over(benchmark, run_d, h)
                if pick_ret is None or bench_ret is None:
                    continue

                self.conn.execute(
                    "INSERT INTO evaluations VALUES (?,?,?,?,?,?)",
                    (
                        pick_id,
                        h,
                        round(pick_ret, 3),
                        round(bench_ret, 3),
                        round(pick_ret - bench_ret, 3),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                n_evaluated += 1
        self.conn.commit()
        return n_evaluated

    # ── reporting ────────────────────────────────────────────────────
    def summary(self) -> dict:
        out: dict = {"horizons": {}}
        for (h,) in self.conn.execute(
            "SELECT DISTINCT horizon_days FROM evaluations"
        ).fetchall():
            row = self.conn.execute(
                "SELECT COUNT(*), AVG(pick_return_pct), AVG(excess_return_pct), "
                "SUM(CASE WHEN excess_return_pct > 0 THEN 1 ELSE 0 END) "
                "FROM evaluations WHERE horizon_days=?",
                (h,),
            ).fetchone()
            n, avg_ret, avg_excess, n_beat = row
            out["horizons"][h] = {
                "n": n,
                "avg_return_pct": round(avg_ret or 0, 3),
                "avg_excess_vs_benchmark_pct": round(avg_excess or 0, 3),
                "hit_rate_vs_benchmark": round((n_beat or 0) / n, 3) if n else None,
            }
        out["total_picks"] = self.conn.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
        return out

    def recent_picks(self, n_days: int = 10) -> list[tuple]:
        return self.conn.execute(
            "SELECT run_date, rank, ticker, total_score, catalyst, rationale "
            "FROM picks WHERE run_date >= ? ORDER BY run_date DESC, rank ASC",
            ((date.today() - timedelta(days=n_days)).isoformat(),),
        ).fetchall()


def _return_over(ticker: str, start: date, horizon_days: int) -> float | None:
    """Close-to-close % return from pick date over `horizon_days` trading days."""
    try:
        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=(start + timedelta(days=horizon_days * 2 + 7)).isoformat(),
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        closes = df["Close"].dropna()
        if len(closes) <= horizon_days:
            return None
        return float(closes.iloc[horizon_days] / closes.iloc[0] - 1) * 100
    except Exception as exc:
        print(f"[ledger] eval fetch failed for {ticker}: {exc}")
        return None
