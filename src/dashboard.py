"""Generate a static HTML dashboard (data/index.html).

Self-contained single file with client-side tabs, one per book (stocks,
crypto, ...) — serve it with nginx, `python -m http.server`, or just open
it. Regenerated on every run.
"""
from __future__ import annotations

from datetime import datetime

from .ledger import Ledger
from .position_sizer import StakeExample
from .ranker import RankedPick

CSS = """
:root {
  --paper: #f7f6f2; --ink: #1c2430; --muted: #6b7280;
  --up: #1a7f4e; --down: #b3382c; --line: #d9d6cd; --accent: #274690;
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--paper); color: var(--ink);
  font: 15px/1.55 Georgia, 'Times New Roman', serif;
  max-width: 980px; margin: 0 auto; padding: 40px 24px 80px;
}
h1 { font-size: 26px; font-weight: 600; letter-spacing: .01em; }
.sub { color: var(--muted); font-size: 13px; margin: 4px 0 20px; }
h2 {
  font-size: 13px; text-transform: uppercase; letter-spacing: .14em;
  color: var(--accent); margin: 36px 0 10px; font-weight: 600;
}
h3.market {
  font-size: 11.5px; text-transform: uppercase; letter-spacing: .1em;
  color: var(--ink); margin: 18px 0 6px; font-weight: 600;
}
table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); font-weight: 600; }
.num { font-family: 'SF Mono', ui-monospace, Consolas, monospace; font-size: 13px; text-align: right; }
.pos { color: var(--up); } .neg { color: var(--down); }
.bar { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; min-width: 90px; }
.bar > i { display: block; height: 100%; background: var(--accent); }
.risk { color: var(--muted); font-size: 13px; font-style: italic; }
.empty { padding: 20px; text-align: center; color: var(--muted); border: 1px dashed var(--line); }
.note { margin-top: 40px; padding: 14px 16px; border-left: 3px solid var(--accent);
        background: #eef0f6; font-size: 13px; color: var(--ink); }
.hint { color: var(--muted); font-size: 13px; font-style: italic; margin-bottom: 10px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
         font-weight: 600; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }
.badge.High { background: #e3f3ea; color: var(--up); }
.badge.Medium { background: #fbf1da; color: #8a6d1d; }
.badge.Low { background: #f7e6e3; color: var(--down); }
.tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--line); margin-bottom: 4px; }
.tab-btn {
  font: 600 13px/1 Georgia, serif; letter-spacing: .04em; text-transform: uppercase;
  padding: 10px 16px; border: none; background: none; color: var(--muted); cursor: pointer;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
}
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.glossary { margin-top: 40px; border: 1px solid var(--line); border-radius: 4px; padding: 2px 16px 14px; }
.glossary summary { cursor: pointer; padding: 12px 0; font-size: 13px; font-weight: 600; color: var(--accent);
                     text-transform: uppercase; letter-spacing: .1em; }
.glossary b { display: block; margin-top: 14px; font-size: 13px; }
.glossary dt { font-weight: 600; margin-top: 8px; font-size: 13.5px; }
.glossary dd { color: var(--muted); font-size: 13px; margin: 2px 0 0; }
"""

GLOSSARY = """
<details class="glossary">
<summary>What do these columns mean?</summary>
<div>
<b>Today's ranking</b> (shown per market, e.g. US / EU, when a book covers more than one)
<dl>
<dt>#</dt><dd>Rank within that market's suggestions — 1 is the highest fused score.</dd>
<dt>Ticker / thesis</dt><dd>The symbol, plus the LLM's one-sentence reason it was flagged.</dd>
<dt>Score</dt><dd>The deterministic fused score the ranker actually sorts by — a weighted blend of the
News, Mom, and Gap pen. columns to the right. This is math, not an LLM opinion; the bar shows its
magnitude relative to that market's top pick.</dd>
<dt>Confidence</dt><dd>A Low/Medium/High badge blending the LLM's self-rated certainty with whether news
and momentum actually agree in direction, and how calm the asset's volatility is. Informational only —
it never affects the score or where a pick lands in the ranking.</dd>
<dt>Est. open / close</dt><dd>The LLM's own speculative guess at the % move by the next session's open
and by its close, grounded in the quant context (momentum, RSI, volatility) plus the news. A suggestion,
not a prediction service.</dd>
<dt>Catalyst</dt><dd>The category of news driving the pick, as classified by the LLM (e.g. earnings,
regulatory, macro for stocks; protocol upgrades, hacks, listings for crypto).</dd>
<dt>News</dt><dd>News score component: sentiment &times; materiality, from -1 to 1 — the LLM's raw signal
contribution to the total score.</dd>
<dt>Mom</dt><dd>Momentum score component: a blend of 20-day and 60-day price trend, from -1 to 1.</dd>
<dt>Gap pen.</dt><dd>Gap penalty component, always &le; 0. Punishes news that looks already priced into
the latest price gap — the classic "the move already happened" trap.</dd>
<dt>Main risk</dt><dd>The LLM's one-sentence take on how this specific thesis could fail.</dd>
</dl>
<b>€ example</b>
<dl>
<dt>Stake</dt><dd>A fixed rule sizes each pick by its Confidence tier (Low/Medium/High), capped so the
whole day's suggestions never deploy more than the configured ceiling of the pool — the rest stays in
cash. Purely a sizing example, not a recommendation of how much to risk.</dd>
<dt>% of pool</dt><dd>That stake as a share of the example capital.</dd>
<dt>Est. close P&amp;L</dt><dd>The stake multiplied by that pick's Est. close move guess — what the LLM's
own (speculative) number would imply in euros.</dd>
<dt>Typical daily swing</dt><dd>The stake multiplied by the ticker's <i>actual</i> historical volatility
(one standard deviation, from real price data — not an LLM guess). Usually much bigger than the Est.
close P&amp;L figure, which is the point: a single-day estimate is one hypothesis inside a much wider
range of normal outcomes.</dd>
</dl>
<b>Scorekeeping — picks vs benchmark</b>
<dl>
<dt>Horizon</dt><dd>Trading days after the pick was made that this row evaluates (1-day, 5-day).</dd>
<dt>N</dt><dd>Number of past picks that have matured to this horizon and been scored.</dd>
<dt>Avg return</dt><dd>Average raw % return of the picks themselves over that horizon.</dd>
<dt>Avg excess vs benchmark</dt><dd>Average of (pick return &minus; benchmark return) — the number that
actually matters: did the picks beat just holding the benchmark?</dd>
<dt>Beat rate</dt><dd>Share of evaluated picks whose return beat the benchmark's return over that horizon.</dd>
</dl>
<b>Recent picks</b>
<dl>
<dt>Date / # / Ticker / Score / Catalyst / Thesis</dt><dd>Same meaning as in Today's ranking, logged
historically so you can see what was suggested on past days.</dd>
</dl>
</div>
</details>
"""


def render(books: dict[str, dict], capital_eur: float, out_path: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    names = list(books)

    tab_buttons = "".join(
        f"<button class=\"tab-btn{' active' if i == 0 else ''}\" data-tab=\"{name}\">{books[name]['label']}</button>"
        for i, name in enumerate(names)
    )
    tab_panels = "".join(
        f"<div class=\"tab-panel{' active' if i == 0 else ''}\" id=\"panel-{name}\">"
        f"{_book_html(books[name], capital_eur)}</div>"
        for i, name in enumerate(names)
    )

    html = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Daily Ranker</title><style>{CSS}</style></head><body>
<h1>Daily Ranker</h1>
<div class='sub'>Generated {now} &middot; news + quant fused ranking &middot; research suggestions, not investment advice</div>

<div class='tabs'>{tab_buttons}</div>
{tab_panels}

{GLOSSARY}

<script>
document.querySelectorAll('.tab-btn').forEach(function (btn) {{
  btn.addEventListener('click', function () {{
    document.querySelectorAll('.tab-btn').forEach(function (b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('.tab-panel').forEach(function (p) {{ p.classList.remove('active'); }});
    btn.classList.add('active');
    document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
  }});
}});
</script>
</body></html>"""

    with open(out_path, "w") as f:
        f.write(html)


def _book_html(book: dict, capital_eur: float) -> str:
    groups: dict[str, list[RankedPick]] = book["groups"]
    ledger: Ledger = book["ledger"]

    today_html = _today_ranking_html(groups)
    stake_html = _stake_html(book["stake_examples"], book["stake_summary"], capital_eur)

    s = ledger.summary()
    perf_rows = "".join(
        f"<tr><td>{h} day</td><td class='num'>{v['n']}</td>"
        f"<td class='num {_cls(v['avg_return_pct'])}'>{v['avg_return_pct']:+.2f}%</td>"
        f"<td class='num {_cls(v['avg_excess_vs_benchmark_pct'])}'>{v['avg_excess_vs_benchmark_pct']:+.2f}%</td>"
        f"<td class='num'>{(v['hit_rate_vs_benchmark'] or 0) * 100:.0f}%</td></tr>"
        for h, v in sorted(s["horizons"].items())
    ) or "<tr><td colspan='5' class='risk'>No evaluations yet — picks need a few days to mature.</td></tr>"

    recent_rows = "".join(
        f"<tr><td class='num'>{d}</td><td class='num'>{r}</td><td><b>{t}</b></td>"
        f"<td class='num'>{sc:+.3f}</td><td>{cat}</td><td class='risk'>{rat}</td></tr>"
        for d, r, t, sc, cat, rat in ledger.recent_picks()
    ) or "<tr><td colspan='6' class='risk'>No history yet.</td></tr>"

    return f"""
<h2>Today's ranking</h2>
{today_html}

<h2>&euro;{capital_eur:,.0f} example</h2>
{stake_html}

<h2>Scorekeeping — picks vs benchmark</h2>
<table><tr><th>Horizon</th><th>N</th><th>Avg return</th><th>Avg excess vs benchmark</th><th>Beat rate</th></tr>
{perf_rows}</table>

<h2>Recent picks (10 days)</h2>
<table><tr><th>Date</th><th>#</th><th>Ticker</th><th>Score</th><th>Catalyst</th><th>Thesis</th></tr>
{recent_rows}</table>

<div class='note'><b>Read the scorekeeping table first.</b> Until "avg excess vs benchmark"
is reliably positive across a meaningful sample (30+ evaluations), treat every daily
ranking as an untested hypothesis. Total picks logged so far: {s['total_picks']}.</div>
"""


def _today_ranking_html(groups: dict[str, list[RankedPick]]) -> str:
    if not any(groups.values()):
        return "<div class='empty'>No compelling picks today — the ranker chose to sit out. That is a feature.</div>"

    show_subheadings = len(groups) > 1
    parts = [
        "<div class='hint'>Est. open/close = the LLM's own speculative point-estimate move, "
        "grounded in momentum/RSI/volatility plus the news below — a suggestion, not a prediction "
        "service. Confidence fuses the LLM's self-rated certainty with whether news and momentum "
        "actually agree and how calm the asset is. See the glossary at the bottom for every column.</div>"
    ]

    for market, picks in groups.items():
        if show_subheadings:
            parts.append(f"<h3 class='market'>{market}</h3>")
        if not picks:
            parts.append(f"<div class='empty'>No compelling {market} picks today.</div>")
            continue

        max_score = max((abs(p.total_score) for p in picks), default=1) or 1
        rows = "".join(
            f"<tr><td class='num'>{i}</td><td><b>{p.ticker}</b><br>"
            f"<span class='risk'>{p.rationale}</span></td>"
            f"<td><div class='bar'><i style='width:{abs(p.total_score) / max_score * 100:.0f}%'></i></div>"
            f"<span class='num'>{p.total_score:+.3f}</span></td>"
            f"<td><span class='badge {p.confidence_label}'>{p.confidence_label}</span></td>"
            f"<td class='num'>open {p.est_open_move_pct:+.1f}%<br>close {p.est_close_move_pct:+.1f}%</td>"
            f"<td>{p.catalyst}</td>"
            f"<td class='num'>{p.news_score:+.2f}</td>"
            f"<td class='num'>{p.momentum_score:+.2f}</td>"
            f"<td class='num'>{p.gap_penalty:+.2f}</td>"
            f"<td class='risk'>{p.risk}</td></tr>"
            for i, p in enumerate(picks, 1)
        )
        parts.append(
            "<table><tr><th>#</th><th>Ticker / thesis</th><th>Score</th><th>Confidence</th>"
            "<th>Est. open / close</th><th>Catalyst</th>"
            "<th>News</th><th>Mom</th><th>Gap pen.</th><th>Main risk</th></tr>"
            f"{rows}</table>"
        )

    return "".join(parts)


def _stake_html(stake_examples: list[StakeExample], summary: dict, capital_eur: float) -> str:
    if not stake_examples:
        return "<div class='empty'>No suggestions today, so nothing to size.</div>"

    rows = "".join(
        f"<tr><td><b>{s.ticker}</b></td><td class='num'>&euro;{s.stake_eur:,.2f}</td>"
        f"<td class='num'>{s.stake_pct:.1f}%</td>"
        f"<td class='num {_cls(s.est_close_pnl_eur)}'>{_eur_signed(s.est_close_pnl_eur)}</td>"
        f"<td class='num'>&plusmn;&euro;{s.typical_daily_swing_eur:,.2f}</td></tr>"
        for s in stake_examples
    )

    scaled_note = (
        " (today's stakes were scaled down to stay within that ceiling)"
        if summary["scaled_down"]
        else ""
    )

    return f"""
<div class='hint'>Illustrative only: a fixed rule sizes each pick by its Confidence tier, never
deploying more than the pool's ceiling across all of today's picks{scaled_note}. Est. close P&amp;L
applies the LLM's own guess to that stake; Typical daily swing applies the ticker's real historical
volatility instead — usually much wider than the guess. Not a plan, not investment advice.</div>
<table><tr><th>Ticker</th><th>Stake</th><th>% of pool</th><th>Est. close P&amp;L</th><th>Typical daily swing</th></tr>
{rows}</table>
<div class='note'><b>If you sized every suggestion today this way:</b> about
&euro;{summary['total_stake_eur']:,.2f} staked ({summary['total_stake_pct']:.1f}% of the
&euro;{capital_eur:,.0f} pool, &euro;{summary['cash_left_eur']:,.2f} left in cash). The LLM's own
guesses imply roughly {_eur_signed(summary['est_close_pnl_eur'])} combined by the close — but real daily
swings for these names are typically much wider, around &plusmn;&euro;{summary['typical_daily_swing_eur']:,.2f}.
Treat the P&amp;L figure as one hypothesis inside that much wider range, not a forecast.</div>
"""


def _cls(x: float) -> str:
    return "pos" if x > 0 else "neg" if x < 0 else ""


def _eur_signed(x: float) -> str:
    """Format a signed euro amount, avoiding an ugly '-€0.00' for near-zero values."""
    if abs(x) < 0.005:
        x = 0.0
    return f"+&euro;{x:,.2f}" if x >= 0 else f"-&euro;{-x:,.2f}"
