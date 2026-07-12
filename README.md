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
RSS news ──► news_fetcher ──┐
                            ├──► llm_analyzer (Claude: sentiment,
yfinance ──► market_data ───┘     materiality, priced-in?)
                 │                        │
                 └────────► ranker ◄──────┘   deterministic fusion
                              │
              ┌───────────────┼──────────────┐
              ▼               ▼              ▼
        ledger.sqlite   rankings.csv   dashboard.html
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

- Claude API: roughly a few cents per run (one Sonnet call with ~60 headlines).
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
