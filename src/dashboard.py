"""Generate a static HTML dashboard (data/index.html).

Self-contained single file with client-side tabs, one per book (stocks,
crypto, ...) — serve it with nginx, `python -m http.server`, or just open
it. Regenerated on every run.

Language on this page is written for someone with no trading background —
plain words over jargon, short sentences, no unexplained numbers. If you add
a column, add a plain-English header AND a glossary entry for it.
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
  font: 16px/1.6 Georgia, 'Times New Roman', serif;
  max-width: 980px; margin: 0 auto; padding: 40px 24px 80px;
}
h1 { font-size: 26px; font-weight: 600; letter-spacing: .01em; }
.sub { color: var(--muted); font-size: 14px; margin: 6px 0 4px; max-width: 640px; }
.sub2 { color: var(--muted); font-size: 12.5px; margin: 0 0 24px; }
h2 {
  font-size: 13px; text-transform: uppercase; letter-spacing: .14em;
  color: var(--accent); margin: 36px 0 6px; font-weight: 600;
}
h2 .plain { display: block; text-transform: none; letter-spacing: 0; color: var(--ink);
            font-size: 15px; margin-top: 4px; font-weight: 400; font-style: italic; }
h3.market {
  font-size: 11.5px; text-transform: uppercase; letter-spacing: .1em;
  color: var(--ink); margin: 18px 0 6px; font-weight: 600;
}
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 10px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 12px; color: var(--muted); font-weight: 600; }
.num { font-family: 'SF Mono', ui-monospace, Consolas, monospace; font-size: 13.5px; text-align: right; }
.pos { color: var(--up); } .neg { color: var(--down); }
.bar { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; min-width: 90px; }
.bar > i { display: block; height: 100%; background: var(--accent); }
.risk { color: var(--muted); font-size: 13.5px; font-style: italic; }
.empty { padding: 20px; text-align: center; color: var(--muted); border: 1px dashed var(--line); }
.note { margin-top: 16px; padding: 14px 16px; border-left: 3px solid var(--accent);
        background: #eef0f6; font-size: 14px; color: var(--ink); }
.hint { color: var(--muted); font-size: 14px; margin-bottom: 14px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
         font-weight: 600; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }
.badge.High { background: #e3f3ea; color: var(--up); }
.badge.Medium { background: #fbf1da; color: #8a6d1d; }
.badge.Low { background: #f7e6e3; color: var(--down); }
.tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--line); margin: 18px 0 4px; }
.tab-btn {
  font: 600 13px/1 Georgia, serif; letter-spacing: .04em; text-transform: uppercase;
  padding: 10px 16px; border: none; background: none; color: var(--muted); cursor: pointer;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
}
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.glossary { margin-top: 40px; border: 1px solid var(--line); border-radius: 4px; padding: 2px 16px 14px; }
.glossary summary { cursor: pointer; padding: 12px 0; font-size: 14px; font-weight: 600; color: var(--accent); }
.glossary b { display: block; margin-top: 14px; font-size: 14px; }
.glossary dt { font-weight: 600; margin-top: 10px; font-size: 14px; }
.glossary dd { color: var(--muted); font-size: 14px; margin: 2px 0 0; }
"""

# Raw catalyst codes -> plain-English labels shown on the page.
CATALYST_LABELS = {
    "earnings_beat": "Earnings beat expectations",
    "guidance": "Company changed its outlook",
    "mna": "Merger or acquisition news",
    "regulatory": "Government or regulatory news",
    "macro": "Big-picture economic or world news",
    "analyst": "An analyst changed their opinion",
    "product": "New product news",
    "protocol_upgrade": "A technical upgrade",
    "hack_exploit": "A hack or security issue",
    "listing_delisting": "Added to or removed from an exchange",
    "whale_activity": "A big investor made a move",
    "adoption": "More people or companies using it",
    "other": "Other news",
}

GLOSSARY = """
<details class="glossary">
<summary>New here? Read this first — what everything on this page means</summary>
<div>
<b>What is this page?</b>
<p style="color:var(--muted); font-size:14px; margin-top:4px;">Every day, an AI reads financial news
and looks at price charts, then a simple, fixed formula (not the AI) turns that into a short list of
stocks, ETFs, or cryptocurrencies that might be worth a look. Nothing here is bought or sold
automatically — it's just a suggestion, and it's tracked over time so you can see whether it's actually
any good.</p>

<b>Today's picks</b>
<dl>
<dt>Strength</dt><dd>A single number and bar showing how strongly the news and the price chart agree
with each other. Bigger bar = stronger case. This comes from a fixed formula, not from the AI's opinion —
it's math you could redo by hand.</dd>
<dt>How sure is the AI?</dt><dd>Low, Medium, or High. This is separate from Strength — a pick can have a
strong case but the AI still isn't very sure about it (thin or mixed news, for example). The less sure it
is, the smaller the suggested amount in the &euro;1,000 example below.</dd>
<dt>AI's guess</dt><dd>The AI's own rough guess at how much the price might move by tomorrow's open and
by tomorrow's close. This is a guess, not a promise — it's often wrong, and that's expected.</dd>
<dt>Why</dt><dd>The kind of news behind the pick (e.g. earnings, big economic news, a hack).</dd>
<dt>What could go wrong</dt><dd>The AI's own one-line note on the most likely way this pick doesn't
work out.</dd>
</dl>

<b>The &euro;1,000 example</b>
<p style="color:var(--muted); font-size:14px; margin-top:4px;">Explained in its own section below —
this is just here if you want the short version: it's a "what if" example, not a plan.</p>

<b>How well has this done so far?</b>
<dl>
<dt>Days later</dt><dd>How long after a pick was made this row is looking at — 1 day later, or 5 days
later.</dd>
<dt>Picks checked</dt><dd>How many past picks have reached that many days and been checked.</dd>
<dt>Average result</dt><dd>On average, how much the picks themselves went up or down.</dd>
<dt>Beat the market by</dt><dd>The one number that actually matters: on average, did the picks do
better or worse than simply holding a normal market index? Above zero is good.</dd>
<dt>Won more than the market</dt><dd>Out of all the picks checked, what share did better than just
holding the market index.</dd>
</dl>

<b>What we've suggested recently</b>
<p style="color:var(--muted); font-size:14px; margin-top:4px;">A simple history log of past picks —
same meaning as the columns in Today's picks, above.</p>
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
<div class='sub'>Every day, an AI reads the news and looks at price charts to suggest a few stocks,
ETFs, or cryptocurrencies that might be worth a look — and shows how sure it is. This is not financial
advice, and nothing here buys or sells anything automatically.</div>
<div class='sub2'>Last updated {now}</div>

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
        f"<tr><td>{h} day{'s' if h != 1 else ''} later</td><td class='num'>{v['n']}</td>"
        f"<td class='num {_cls(v['avg_return_pct'])}'>{v['avg_return_pct']:+.2f}%</td>"
        f"<td class='num {_cls(v['avg_excess_vs_benchmark_pct'])}'>{v['avg_excess_vs_benchmark_pct']:+.2f}%</td>"
        f"<td class='num'>{(v['hit_rate_vs_benchmark'] or 0) * 100:.0f}%</td></tr>"
        for h, v in sorted(s["horizons"].items())
    ) or "<tr><td colspan='5' class='risk'>No picks have matured yet — check back in a few days.</td></tr>"

    recent_rows = "".join(
        f"<tr><td class='num'>{d}</td><td class='num'>{r}</td><td><b>{t}</b></td>"
        f"<td class='num'>{sc:+.3f}</td><td>{_catalyst_label(cat)}</td><td class='risk'>{rat}</td></tr>"
        for d, r, t, sc, cat, rat in ledger.recent_picks()
    ) or "<tr><td colspan='6' class='risk'>Nothing suggested yet.</td></tr>"

    return f"""
<h2>Today's picks</h2>
{today_html}

<h2>The &euro;{capital_eur:,.0f} example<span class='plain'>What would happen if you tried this with &euro;{capital_eur:,.0f}?</span></h2>
{stake_html}

<h2>How well has this done so far?<span class='plain'>Compared with just holding the normal market</span></h2>
<table><tr><th>Days later</th><th>Picks checked</th><th>Average result</th><th>Beat the market by</th><th>Won more than the market</th></tr>
{perf_rows}</table>
<div class='note'><b>Read this table before the picks above.</b> Until "Beat the market by" is reliably
above zero over many picks (30+), treat every pick as an untested guess, not a proven strategy.
Picks logged so far: {s['total_picks']}.</div>

<h2>What we've suggested recently<span class='plain'>Last 10 days</span></h2>
<table><tr><th>Date</th><th>#</th><th>Ticker</th><th>Strength</th><th>Why</th><th>What the AI said</th></tr>
{recent_rows}</table>
"""


def _today_ranking_html(groups: dict[str, list[RankedPick]]) -> str:
    if not any(groups.values()):
        return "<div class='empty'>Nothing looked convincing enough today, so no picks are shown. Sitting out on a quiet day is intentional, not a bug.</div>"

    show_subheadings = len(groups) > 1
    parts = [
        "<div class='hint'>\"AI's guess\" is the AI's own rough estimate, not a promise — it's often "
        "wrong. \"How sure\" tells you how much weight to put on a pick; the &euro;1,000 example below "
        "uses it to suggest smaller amounts for less-sure picks.</div>"
    ]

    for market, picks in groups.items():
        if show_subheadings:
            parts.append(f"<h3 class='market'>{market}</h3>")
        if not picks:
            parts.append(f"<div class='empty'>Nothing convincing in {market} today.</div>")
            continue

        max_score = max((abs(p.total_score) for p in picks), default=1) or 1
        rows = "".join(
            f"<tr><td class='num'>{i}</td><td><b>{p.ticker}</b><br>"
            f"<span class='risk'>{p.rationale}</span></td>"
            f"<td><div class='bar'><i style='width:{abs(p.total_score) / max_score * 100:.0f}%'></i></div>"
            f"<span class='num'>{p.total_score:+.3f}</span></td>"
            f"<td><span class='badge {p.confidence_label}'>{p.confidence_label}</span></td>"
            f"<td class='num'>tomorrow open {p.est_open_move_pct:+.1f}%<br>tomorrow close {p.est_close_move_pct:+.1f}%</td>"
            f"<td>{_catalyst_label(p.catalyst)}</td>"
            f"<td class='risk'>{p.risk}</td></tr>"
            for i, p in enumerate(picks, 1)
        )
        parts.append(
            "<table><tr><th>#</th><th>Ticker / why it's here</th><th>Strength</th><th>How sure is the AI?</th>"
            "<th>AI's guess</th><th>Why</th><th>What could go wrong</th></tr>"
            f"{rows}</table>"
        )

    return "".join(parts)


def _stake_html(stake_examples: list[StakeExample], summary: dict, capital_eur: float) -> str:
    if not stake_examples:
        return "<div class='empty'>No picks today, so there's nothing to try this with.</div>"

    rows = "".join(
        f"<tr><td><b>{s.ticker}</b></td><td class='num'>&euro;{s.stake_eur:,.2f}"
        f"<div class='risk' style='font-style:normal;'>{s.stake_pct:.1f}% of your money</div></td>"
        f"<td class='num {_cls(s.est_close_pnl_eur)}'>{_eur_signed(s.est_close_pnl_eur)}</td>"
        f"<td class='num'>&plusmn;&euro;{s.typical_daily_swing_eur:,.2f}</td></tr>"
        for s in stake_examples
    )

    scaled_note = (
        " (today the amounts below were made smaller across the board to stay under that limit)"
        if summary["scaled_down"]
        else ""
    )

    return f"""
<div class='hint'>Here's a simple example, not a plan: imagine you had &euro;{capital_eur:,.0f} and tried
a small amount on each pick above. The less sure the AI is about a pick, the smaller the suggested
amount — and no matter how many picks show up, this never suggests trying more than half your money in
one day{scaled_note}. The rest stays untouched, as cash.</div>
<table><tr><th>Pick</th><th>Amount to try</th><th>If the AI's guess comes true</th><th>How much it normally moves in a day anyway</th></tr>
{rows}</table>
<div class='note'>
<p><b>In plain terms:</b> if you'd tried every pick above this way, you'd put in about
&euro;{summary['total_stake_eur']:,.2f} in total — {summary['total_stake_pct']:.1f}% of your
&euro;{capital_eur:,.0f} — leaving &euro;{summary['cash_left_eur']:,.2f} untouched.</p>
<p style="margin-top:8px;">If the AI's guesses all came true, that adds up to roughly
{_eur_signed(summary['est_close_pnl_eur'])} by the end of the day. But look at the last column above:
these prices normally move around by about &plusmn;&euro;{summary['typical_daily_swing_eur']:,.2f} on
an ordinary day anyway — usually more than the AI's guess. So don't read the AI's guess as a forecast;
it's one small hypothesis inside a much bigger range of normal, everyday ups and downs.</p>
</div>
"""


def _catalyst_label(code: str) -> str:
    return CATALYST_LABELS.get(code, code.replace("_", " ").capitalize())


def _cls(x: float) -> str:
    return "pos" if x > 0 else "neg" if x < 0 else ""


def _eur_signed(x: float) -> str:
    """Format a signed euro amount, avoiding an ugly '-€0.00' for near-zero values."""
    if abs(x) < 0.005:
        x = 0.0
    return f"+&euro;{x:,.2f}" if x >= 0 else f"-&euro;{-x:,.2f}"
