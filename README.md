# Daily Ranker

Self-hosted research assistant: reads overnight financial news, pulls
historical price data, asks Claude to judge news sentiment/materiality,
fuses that with quantitative features, and outputs a ranked daily list of
EU + US stocks/ETFs — plus a ledger that scores every past pick against
a benchmark so you know whether the system is actually any good.

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

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python main.py
```

Outputs land in `data/`: `dashboard.html`, `rankings.csv`, `ledger.sqlite`.

## Serving the dashboard

Any static file server works:

```bash
cd data && python -m http.server 8080     # quick and dirty
# or point nginx at /opt/daily-ranker/data/dashboard.html
```

## Cron (Berlin time; EU pre-open run + evening evaluation)

```cron
30 7  * * 1-5  cd /opt/daily-ranker && ./venv/bin/python main.py >> data/run.log 2>&1
0  22 * * 1-5  cd /opt/daily-ranker && ./venv/bin/python main.py --eval >> data/run.log 2>&1
```

## Cost

- Claude API: roughly a few cents per run (one Sonnet call with ~60 headlines).
- Data: yfinance + RSS, free. Delayed data — fine for ranking, never for execution.
- Hosting: any €5/month VPS, a Raspberry Pi, or GitHub Actions on a schedule.

## Tuning

- `config.yaml → ranking.weights` — refit these only after the ledger has
  30+ evaluations; earlier tuning is curve-fitting to noise.
- Universe: add/remove tickers freely (yfinance suffixes: `.DE` Xetra,
  `.PA` Paris, `.AS` Amsterdam, `.SW` SIX). Verify each ETF ticker resolves
  in yfinance before relying on it.
- News: add sector-specific RSS feeds for better coverage of EU names —
  the default feeds skew US.

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
