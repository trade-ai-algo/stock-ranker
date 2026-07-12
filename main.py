"""Daily Ranker — main entrypoint.

Usage:
    python main.py            # full run: news -> quant -> LLM -> rank -> log -> dashboard
    python main.py --eval     # only evaluate matured past picks + refresh dashboard

Cron example (07:30 Berlin time, before EU open; US premarket news included):
    30 7 * * 1-5  cd /opt/daily-ranker && /usr/bin/python3 main.py >> data/run.log 2>&1
    0  22 * * 1-5 cd /opt/daily-ranker && /usr/bin/python3 main.py --eval >> data/run.log 2>&1
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

import yaml

from src.dashboard import render
from src.ledger import Ledger
from src.llm_analyzer import analyze_news
from src.market_data import fetch_features
from src.news_fetcher import fetch_headlines
from src.ranker import rank


def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml") as f:
        return yaml.safe_load(f)


def main() -> None:
    cfg = load_config()
    ledger = Ledger(cfg["ledger"]["db_path"])

    eval_only = "--eval" in sys.argv

    # Always evaluate matured picks first — cheap and keeps the ledger fresh.
    n = ledger.evaluate_due(cfg["ledger"]["eval_horizons_days"], cfg["benchmark"])
    print(f"[eval] evaluated {n} matured picks")

    picks = []
    if not eval_only:
        tickers = cfg["universe"]["stocks"] + cfg["universe"]["etfs"]

        print("[1/4] fetching news…")
        headlines = fetch_headlines(
            cfg["news"]["rss_feeds"],
            cfg["news"]["lookback_hours"],
            cfg["news"]["max_headlines"],
        )
        print(f"      {len(headlines)} headlines")

        print("[2/4] fetching market data + features…")
        features = fetch_features(
            tickers,
            cfg["features"]["history_days"],
            cfg["features"]["momentum_windows"],
            cfg["features"]["vol_window"],
            cfg["features"]["rsi_window"],
        )
        print(f"      {len(features)} tickers with features")

        print("[3/4] LLM news analysis…")
        llm_scores = analyze_news(
            headlines, features, cfg["llm"]["model"], cfg["llm"]["max_tokens"]
        )
        print(f"      {len(llm_scores)} tickers flagged by news")

        print("[4/4] ranking…")
        picks = rank(
            llm_scores,
            features,
            cfg["ranking"]["weights"],
            cfg["ranking"]["top_n"],
            cfg["ranking"]["allow_no_pick"],
            cfg["ranking"].get("min_score", 0.10),
        )

        if picks:
            ledger.log_picks(date.today(), picks)
            _append_csv(cfg["output"]["csv_path"], picks)
            for i, p in enumerate(picks, 1):
                print(
                    f"  {i}. {p.ticker:8s} score={p.total_score:+.3f} conf={p.confidence_label:6s} "
                    f"est_open={p.est_open_move_pct:+.1f}% est_close={p.est_close_move_pct:+.1f}% "
                    f"[{p.catalyst}] {p.rationale}"
                )
        else:
            print("  no compelling picks today (allow_no_pick=true) — sitting out")

    render(picks, ledger, "data/index.html")
    print("[done] dashboard written to data/index.html")


def _append_csv(path: str, picks) -> None:
    exists = Path(path).exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(
                ["date", "rank", "ticker", "score", "catalyst", "rationale", "risk", "close",
                 "confidence_label", "confidence_score", "est_open_move_pct", "est_close_move_pct"]
            )
        for i, p in enumerate(picks, 1):
            w.writerow(
                [date.today(), i, p.ticker, p.total_score, p.catalyst, p.rationale, p.risk, p.last_close,
                 p.confidence_label, p.confidence_score, p.est_open_move_pct, p.est_close_move_pct]
            )


if __name__ == "__main__":
    main()
