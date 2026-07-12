"""Daily Ranker — main entrypoint.

Usage:
    python main.py            # full run: news -> quant -> LLM -> rank -> log -> dashboard, per book
    python main.py --eval     # only evaluate matured past picks + refresh dashboard

Runs the identical pipeline once per "book" defined in config.yaml (stocks,
crypto, ...) and renders every book into its own tab on one dashboard page.

Cron example (07:00 UTC = 9AM Berlin time, before EU open; US premarket news included):
    0  7  * * 1-5  cd /opt/daily-ranker && /usr/bin/python3 main.py >> data/run.log 2>&1
    0  20 * * 1-5  cd /opt/daily-ranker && /usr/bin/python3 main.py --eval >> data/run.log 2>&1
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


def run_book(name: str, book_cfg: dict, cfg: dict, eval_only: bool) -> dict:
    ledger = Ledger(book_cfg["ledger"]["db_path"])

    n = ledger.evaluate_due(book_cfg["ledger"]["eval_horizons_days"], book_cfg["benchmark"])
    print(f"[{name}][eval] evaluated {n} matured picks")

    picks = []
    if not eval_only:
        tickers = [t for group in book_cfg["universe"].values() for t in group]

        print(f"[{name} 1/4] fetching news…")
        headlines = fetch_headlines(
            book_cfg["news"]["rss_feeds"],
            book_cfg["news"]["lookback_hours"],
            book_cfg["news"]["max_headlines"],
        )
        print(f"      {len(headlines)} headlines")

        print(f"[{name} 2/4] fetching market data + features…")
        features = fetch_features(
            tickers,
            cfg["features"]["history_days"],
            cfg["features"]["momentum_windows"],
            cfg["features"]["vol_window"],
            cfg["features"]["rsi_window"],
        )
        print(f"      {len(features)} tickers with features")

        print(f"[{name} 3/4] LLM news analysis…")
        llm_scores = analyze_news(
            headlines,
            features,
            cfg["llm"]["model"],
            cfg["llm"]["max_tokens"],
            book_cfg["asset_label"],
            book_cfg["catalyst_options"],
        )
        print(f"      {len(llm_scores)} tickers flagged by news")

        print(f"[{name} 4/4] ranking…")
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
            _append_csv(book_cfg["output"]["csv_path"], picks)
            for i, p in enumerate(picks, 1):
                print(
                    f"  {i}. {p.ticker:8s} score={p.total_score:+.3f} conf={p.confidence_label:6s} "
                    f"est_open={p.est_open_move_pct:+.1f}% est_close={p.est_close_move_pct:+.1f}% "
                    f"[{p.catalyst}] {p.rationale}"
                )
        else:
            print(f"  [{name}] no compelling picks today (allow_no_pick=true) — sitting out")

    return {"label": book_cfg["label"], "picks": picks, "ledger": ledger}


def main() -> None:
    cfg = load_config()
    eval_only = "--eval" in sys.argv

    books = {name: run_book(name, book_cfg, cfg, eval_only) for name, book_cfg in cfg["books"].items()}

    render(books, "data/index.html")
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
