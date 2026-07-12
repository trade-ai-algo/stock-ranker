# Deployment Guide

## Option A — GitHub Actions + Pages (€0, recommended)

No server. Actions runs the ranker on schedule, commits results back to the
repo, and publishes the dashboard to GitHub Pages.

**Trade-off to accept first:** free-tier Pages requires a **public repo**,
so your dashboard, picks, and ledger history are public. No secrets are in
them (the API key lives in GitHub Secrets), but your picks are visible.
If you want privacy: use Option B, or pay for GitHub Pro (private Pages).

### Steps (~10 minutes)

1. Create a new GitHub repo (public), push this project to it:
   ```bash
   git init && git add -A && git commit -m "initial"
   git branch -M main
   git remote add origin git@github.com:YOURNAME/daily-ranker.git
   git push -u origin main
   ```
2. Repo → **Settings → Secrets and variables → Actions → New repository
   secret**: name `ANTHROPIC_API_KEY`, value your key.
3. Repo → **Settings → Pages → Source: GitHub Actions**.
4. Repo → **Actions** tab → select `daily-ranker` → **Run workflow** to
   test manually. First run takes ~2 min.
5. Dashboard appears at `https://YOURNAME.github.io/daily-ranker/`.

The schedule is defined in `.github/workflows/daily.yml`. Notes:

- GitHub cron is **UTC** and does not follow DST — the 05:30 UTC run is
  07:30 Berlin in summer but 06:30 in winter. Adjust twice a year or live
  with it (both are fine: still pre-EU-open).
- Scheduled runs on free tier can start up to ~15 min late. Irrelevant
  for daily ranking.
- GitHub disables schedules on repos with no activity for 60 days — the
  bot's own data commits keep it alive automatically.
- State (ledger.sqlite, rankings.csv) is persisted by committing `data/`
  back to the repo each run.

### Cost
€0 infra + a few cents/day Claude API ≈ **under €1/month total**.

## Option B — Any small VPS (~€0–4/month, private)

Oracle Cloud "Always Free" ARM instance (€0) or Hetzner CX11 (~€4).

```bash
sudo apt update && sudo apt install -y python3-venv git nginx
git clone <your-repo> /opt/daily-ranker && cd /opt/daily-ranker
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.profile
crontab -e   # add the two lines from README.md
```

Serve `data/` with nginx (add basic auth for privacy):

```nginx
server {
  listen 80;
  root /opt/daily-ranker/data;
  index index.html;
  auth_basic "ranker";
  auth_basic_user_file /etc/nginx/.htpasswd;  # htpasswd -c ... youruser
}
```

Or use the Dockerfile — see comments at its top.

## Option C — Raspberry Pi at home (€0 marginal)

Identical to Option B minus the VPS. Access the dashboard on your LAN, or
via Tailscale (free) from anywhere without exposing anything publicly.

## Which to pick

- Want zero ops and don't mind public picks → **A**
- Want privacy / an always-on box for future projects (e.g. the IBKR
  backtester) → **B** (Oracle free tier if the signup gods allow, else
  Hetzner)
- Own a Pi → **C**
