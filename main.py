"""Daily Ranker — main entrypoint.

Usage:
    python main.py            # full run: news -> quant -> LLM -> rank -> log -> dashboard, per book
    python main.py --eval     # only evaluate matured past picks + refresh dashboard

Runs the identical pipeline once per "book" defined in config.yaml (stocks,
crypto, ...), each book's universe nested by market (e.g. US / EU), plus a
web-search-discovered "Trending" group per book, and renders every book into
its own tab on one dashboard page.

Cron example (07:00 UTC = 9AM Berlin time, before EU open; US premarket news included):
    0  7  * * 1-5  cd /opt/daily-ranker && /usr/bin/python3 main.py >> data/run.log 2>&1
    0  20 * * 1-5  cd /opt/daily-ranker && /usr/bin/python3 main.py --eval >> data/run.log 2>&1
"""
from __future__ import annotations

import csv
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from src.dashboard import render
from src.ledger import Ledger
from src.llm_analyzer import analyze_news
from src.market_data import fetch_features
from src.news_fetcher import Headline, fetch_headlines
from src.position_sizer import size_book
from src.ranker import rank_by_group
from src.ticker_discovery import discover_tickers

TRENDING_GROUP = "Trending"


def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml") as f:
        return yaml.safe_load(f)


def run_book(name: str, book_cfg: dict, cfg: dict, eval_only: bool) -> dict:
    ledger = Ledger(book_cfg["ledger"]["db_path"])

    n = ledger.evaluate_due(book_cfg["ledger"]["eval_horizons_days"], book_cfg["benchmark"])
    print(f"[{name}][eval] evaluated {n} matured picks")

    groups: dict[str, list] = {m: [] for m in book_cfg["universe"]}
    if not eval_only:
        tickers = [t for market in book_cfg["universe"].values() for grp in market.values() for t in grp]
        ticker_market = {
            t: market for market, groups_ in book_cfg["universe"].items() for grp in groups_.values() for t in grp
        }

        print(f"[{name} 1/5] fetching news…")
        headlines = fetch_headlines(
            book_cfg["news"]["rss_feeds"],
            book_cfg["news"]["lookback_hours"],
            book_cfg["news"]["max_headlines"],
        )
        print(f"      {len(headlines)} headlines")

        disc_cfg = book_cfg.get("discovery", {})
        if disc_cfg.get("enabled"):
            print(f"[{name} 2/5] searching the web for tickers beyond the watchlist…")
            candidates = discover_tickers(cfg["llm"]["model"], book_cfg["asset_label"], disc_cfg.get("max_searches", 4))
            new_tickers = [c["ticker"] for c in candidates if c["ticker"] not in ticker_market]
            for t in new_tickers:
                ticker_market[t] = TRENDING_GROUP
            tickers += new_tickers
            now = datetime.now(timezone.utc)
            headlines += [
                Headline(title=f"{c['ticker']}: {c.get('why', '')}", summary=c.get("why", ""),
                         source="web search", published=now, link="")
                for c in candidates if c["ticker"] in new_tickers
            ]
            print(f"      {len(new_tickers)} new tickers found")
        else:
            print(f"[{name} 2/5] web search disabled for this book, skipping")

        print(f"[{name} 3/5] fetching market data + features…")
        features = fetch_features(
            tickers,
            cfg["features"]["history_days"],
            cfg["features"]["momentum_windows"],
            cfg["features"]["vol_window"],
            cfg["features"]["rsi_window"],
            cfg["features"].get("min_history_days"),
            cfg["features"].get("ipo_lookback_days", 90),
        )
        min_adv = disc_cfg.get("min_adv_musd", 0.0)
        illiquid = [
            t for t, f in features.items()
            if ticker_market.get(t) == TRENDING_GROUP and f.avg_dollar_volume_m < min_adv
        ]
        for t in illiquid:
            del features[t]
        if illiquid:
            print(f"      dropped {len(illiquid)} discovered ticker(s) below the liquidity floor")
        print(f"      {len(features)} tickers with features")

        print(f"[{name} 4/5] LLM news analysis…")
        llm_scores = analyze_news(
            headlines,
            features,
            cfg["llm"]["model"],
            cfg["llm"]["max_tokens"],
            book_cfg["asset_label"],
            book_cfg["catalyst_options"],
        )
        print(f"      {len(llm_scores)} tickers flagged by news")

        print(f"[{name} 5/5] ranking…")
        groups = rank_by_group(
            llm_scores,
            features,
            ticker_market,
            cfg["ranking"]["weights"],
            cfg["ranking"]["top_n"],
            cfg["ranking"]["allow_no_pick"],
            cfg["ranking"].get("min_score", 0.10),
        )

        any_picks = False
        for market, picks in groups.items():
            if not picks:
                continue
            any_picks = True
            ledger.log_picks(date.today(), picks)
            _append_csv(book_cfg["output"]["csv_path"], picks)
            print(f"  [{market}]")
            for i, p in enumerate(picks, 1):
                ipo_tag = " IPO" if p.is_ipo else ""
                print(
                    f"    {i}. {p.ticker:8s}{ipo_tag} score={p.total_score:+.3f} conf={p.confidence_label:6s} "
                    f"est_open={p.est_open_move_pct:+.1f}% est_close={p.est_close_move_pct:+.1f}% "
                    f"[{p.catalyst}] {p.rationale}"
                )
        if not any_picks:
            print(f"  [{name}] no compelling picks today (allow_no_pick=true) — sitting out")

    all_picks = [p for picks in groups.values() for p in picks]
    stake_examples, stake_summary = size_book(
        all_picks,
        cfg["simulation"]["capital_eur"],
        cfg["simulation"]["stake_pct_by_confidence"],
        cfg["simulation"]["max_total_deployed_pct"],
    )

    return {
        "label": book_cfg["label"],
        "groups": groups,
        "ledger": ledger,
        "stake_examples": stake_examples,
        "stake_summary": stake_summary,
    }


def main() -> None:
    cfg = load_config()
    eval_only = "--eval" in sys.argv

    books = {name: run_book(name, book_cfg, cfg, eval_only) for name, book_cfg in cfg["books"].items()}

    render(books, cfg["simulation"]["capital_eur"], "data/index.html")
    print("[done] dashboard written to data/index.html")


def _append_csv(path: str, picks) -> None:
    exists = Path(path).exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(
                ["date", "rank", "ticker", "score", "catalyst", "rationale", "risk", "close",
                 "confidence_label", "confidence_score", "est_open_move_pct", "est_close_move_pct", "is_ipo"]
            )
        for i, p in enumerate(picks, 1):
            w.writerow(
                [date.today(), i, p.ticker, p.total_score, p.catalyst, p.rationale, p.risk, p.last_close,
                 p.confidence_label, p.confidence_score, p.est_open_move_pct, p.est_close_move_pct, p.is_ipo]
            )


if __name__ == "__main__":
    main()
