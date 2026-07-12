# Daily Ranker

Self-hosted research assistant: reads overnight news, pulls historical price
data, asks Claude to judge sentiment/materiality, fuses that with
quantitative features, and outputs a ranked daily list — plus a ledger that
scores every past pick against a benchmark so you know whether the system is
actually any good. Runs two independent "books" through the identical
pipeline, each its own tab on the dashboard: **Stocks & ETFs** (EU + US,
ranked independently per market so one doesn't crowd out the other) and
**Crypto** (top 5). Add more asset classes/markets by extending
`config.yaml → books`.

**This produces research suggestions, not investment advice, and it does
not trade.** The ledger exists precisely because the picks are hypotheses
until proven otherwise.

## Architecture

```
RSS news ──────────────► news_fetcher ──┐
web search (Claude) ──► ticker_discovery ┤
                                          ├──► llm_analyzer (Claude: sentiment,
yfinance ──────────────► market_data ────┘     materiality, priced-in?)
                 │                        │
                 └────────► ranker ◄──────┘   deterministic fusion
                              │
              ┌───────────────┼──────────────┐
              ▼               ▼              ▼
        ledger.sqlite   rankings.csv   dashboard/index.html
        (scorekeeping)                 (serve statically)
```

Design principles baked in:

- **The LLM never ranks.** It only scores news (sentiment × materiality ×
  priced-in). The final ranking is deterministic math you can audit.
- **"No pick" is a valid output.** Weak days produce an empty list instead
  of forced noise (`allow_no_pick: true`, bar set by `ranking.min_score`).
- **Confidence is informational, never a ranking input.** Each pick carries a
  Low/Medium/High confidence badge fusing the LLM's self-rated certainty with
  whether news and momentum actually agree and how calm the name is — it
  doesn't affect `total_score` or sort order.
- **Open/close move estimates are the LLM's own speculative guess**, grounded
  in the quant context, shown alongside each pick — a suggestion, not a
  prediction service.
- **Priced-in penalty.** The overnight gap is measured and used to punish
  chasing news the market already absorbed — the classic retail trap.
- **The ledger is the product.** Every pick is logged with its price and
  auto-evaluated at 1d/5d vs the benchmark. Trust the summary table, not
  the daily list.
- **The €1000 example is a fixed rule, not a strategy.** Each pick is sized
  by its confidence tier (`simulation.stake_pct_by_confidence`), capped so a
  day's picks never deploy more than `simulation.max_total_deployed_pct` of
  the pool. It shows the LLM's own close-move guess in euros next to the
  ticker's *actual* historical daily volatility in euros — on purpose, so
  the point estimate is visibly dwarfed by real day-to-day noise.
- **Discovery widens the net, never lowers the bar.** `ticker_discovery.py`
  uses Claude's web-search tool to find tickers — including recent IPOs —
  beyond the fixed watchlist, surfaced in their own "Trending" group. They
  go through the exact same liquidity floor, LLM scoring, and `min_score`
  filter as every other ticker; a bad or noisy search just means fewer
  candidates survive, not a worse pick getting through.
- **IPO tagging is computed from real trading history, not guessed by the
  LLM.** A ticker is tagged "IPO" if it has less than `ipo_lookback_days`
  of actual price history — deterministic and can't be prompted into being
  wrong. Names with under `min_history_days` of history (too new to say
  anything statistically meaningful) are left out entirely, on any day.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python main.py
```

Outputs land in `data/`: `index.html` (the dashboard, tabbed per book), and
per-book `rankings*.csv` / `ledger*.sqlite` (e.g. `ledger.sqlite` for stocks,
`ledger_crypto.sqlite` for crypto). Every column on the dashboard is
explained in the "What do these columns mean?" panel at the bottom of the
page.

## Serving the dashboard

Any static file server works:

```bash
cd data && python -m http.server 8080     # quick and dirty
# or point nginx at /opt/daily-ranker/data/dashboard.html
```

## Cron (Berlin time; morning run + evening evaluation)

```cron
0  9  * * 1-5  cd /opt/daily-ranker && ./venv/bin/python main.py >> data/run.log 2>&1
0  22 * * 1-5  cd /opt/daily-ranker && ./venv/bin/python main.py --eval >> data/run.log 2>&1
```

## Cost

- Claude API: roughly a few cents per run for the news-analysis call
  (~60-70 headlines). Web-search discovery adds a small extra cost per
  search, capped at `discovery.max_searches` (default 4) per book per run —
  turn a book's `discovery.enabled` off to skip it entirely.
- Data: yfinance + RSS, free. Delayed data — fine for ranking, never for execution.
- Hosting: any €5/month VPS, a Raspberry Pi, or GitHub Actions on a schedule.

## Tuning

- `config.yaml → ranking.weights` — refit these only after the ledger has
  30+ evaluations; earlier tuning is curve-fitting to noise.
- `ranking.top_n` applies **per market group** (e.g. up to 5 US + 5 EU stock
  picks), not to the book as a whole — each `universe.<Market>` entry gets
  its own independently ranked, independently filtered list.
- Universe: add/remove tickers freely under the right market (yfinance
  suffixes: `.DE` Xetra, `.PA` Paris, `.AS` Amsterdam, `.SW` SIX, `-USD` for
  crypto). Verify each ticker resolves in yfinance before relying on it.
- News: add sector-specific RSS feeds for better coverage of EU names —
  the default feeds skew US.
- `config.yaml → simulation` — tune the confidence → stake-% tiers or the
  deployment ceiling; both only change the illustrative €-example, never
  the ranking itself.
- `config.yaml → books.<book>.discovery` — `min_adv_musd` is the liquidity
  floor for web-discovered tickers (raise it if illiquid/manipulation-prone
  names keep showing up); `max_searches` bounds cost per run.
- `features.min_history_days` / `features.ipo_lookback_days` — how little
  history is enough to include a ticker at all, vs. how little is enough to
  tag it "IPO". Both apply to every ticker, not just discovered ones.

## Honest limitations

- Public news is largely priced in before you can act; the gap penalty
  mitigates but cannot eliminate this.
- yfinance is unofficial and occasionally breaks; wrap in retries or swap
  for a paid API if this becomes production-critical.
- EU/US mixed universe means mixed trading hours — a 07:30 Berlin run sees
  yesterday's US close and this morning's EU pre-open news, which is a
  reasonable but imperfect snapshot.
- Survivorship: judge the system on the ledger's *excess* return vs the
  benchmark, not raw returns — a bull market makes everything look smart.
- Web search can return wrong or hallucinated tickers, or nothing useful on
  a given day; a failed/empty search degrades to just the fixed watchlist,
  it never crashes the run. The liquidity floor helps but doesn't eliminate
  the risk of a discovered name being a thinly-traded or manipulated stock —
  treat "Trending" picks with at least as much skepticism as the rest.
