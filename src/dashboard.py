"""Generate a static HTML dashboard (data/dashboard.html).

Self-contained single file — serve it with nginx, `python -m http.server`,
or just open it. Regenerated on every run.
"""
from __future__ import annotations

from datetime import datetime

from .ledger import Ledger
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
.sub { color: var(--muted); font-size: 13px; margin: 4px 0 28px; }
h2 {
  font-size: 13px; text-transform: uppercase; letter-spacing: .14em;
  color: var(--accent); margin: 36px 0 10px; font-weight: 600;
}
table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); font-weight: 600; }
.num { font-family: 'SF Mono', ui-monospace, Consolas, monospace; font-size: 13px; text-align: right; }
.pos { color: var(--up); } .neg { color: var(--down); }
.bar { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; min-width: 90px; }
.bar > i { display: block; height: 100%; background: var(--accent); }
.risk { color: var(--muted); font-size: 13px; font-style: italic; }
.empty { padding: 28px; text-align: center; color: var(--muted); border: 1px dashed var(--line); }
.note { margin-top: 40px; padding: 14px 16px; border-left: 3px solid var(--accent);
        background: #eef0f6; font-size: 13px; color: var(--ink); }
.hint { color: var(--muted); font-size: 13px; font-style: italic; margin-bottom: 10px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
         font-weight: 600; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }
.badge.High { background: #e3f3ea; color: var(--up); }
.badge.Medium { background: #fbf1da; color: #8a6d1d; }
.badge.Low { background: #f7e6e3; color: var(--down); }
"""


def render(picks: list[RankedPick], ledger: Ledger, out_path: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    max_score = max((abs(p.total_score) for p in picks), default=1) or 1

    if picks:
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
        today_html = (
            "<div class='hint'>Est. open/close = the LLM's own speculative point-estimate move, "
            "grounded in momentum/RSI/volatility plus the news below — a suggestion, not a prediction "
            "service. Confidence fuses the LLM's self-rated certainty with whether news and momentum "
            "actually agree and how calm the name is.</div>"
            "<table><tr><th>#</th><th>Ticker / thesis</th><th>Score</th><th>Confidence</th>"
            "<th>Est. open / close</th><th>Catalyst</th>"
            "<th>News</th><th>Mom</th><th>Gap pen.</th><th>Main risk</th></tr>"
            f"{rows}</table>"
        )
    else:
        today_html = "<div class='empty'>No compelling picks today — the ranker chose to sit out. That is a feature.</div>"

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

    html = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Daily Ranker</title><style>{CSS}</style></head><body>
<h1>Daily Ranker</h1>
<div class='sub'>Generated {now} &middot; news + quant fused ranking &middot; research suggestions, not investment advice</div>

<h2>Today's ranking</h2>
{today_html}

<h2>Scorekeeping — picks vs benchmark</h2>
<table><tr><th>Horizon</th><th>N</th><th>Avg return</th><th>Avg excess vs benchmark</th><th>Beat rate</th></tr>
{perf_rows}</table>

<h2>Recent picks (10 days)</h2>
<table><tr><th>Date</th><th>#</th><th>Ticker</th><th>Score</th><th>Catalyst</th><th>Thesis</th></tr>
{recent_rows}</table>

<div class='note'><b>Read the scorekeeping table first.</b> Until "avg excess vs benchmark"
is reliably positive across a meaningful sample (30+ evaluations), treat every daily
ranking as an untested hypothesis. Total picks logged so far: {s['total_picks']}.</div>
</body></html>"""

    with open(out_path, "w") as f:
        f.write(html)


def _cls(x: float) -> str:
    return "pos" if x > 0 else "neg" if x < 0 else ""
