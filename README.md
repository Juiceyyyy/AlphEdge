# AlphEdge

An Indian-equity momentum research site with a weekday forward model record and an optional **self-hosted** Zerodha Kite account runner. The public site shows historical simulations and the stocks the model would target today. It never connects to a visitor's brokerage account or displays real account balances.

## What you can inspect

- Historical strategy and Nifty 50 results, annual returns, three-year windows, drawdown, and risk-adjusted metrics.
- A lump-sum and monthly-contribution illustration based on saved historical results. Annual-to-monthly interpolation is clearly labelled; an on-demand rerun can show monthly backtest checkpoints.
- Current model stocks and target percentage weights, with the latest price date. A risk-off signal can produce a 100% cash target. A separate forward model index starts at 100 on its first observation and adds a close-to-close observation after each successful refresh for a new market day.
- Switches for the Nifty and individual-stock 200-day moving-average filters, plus target basket size. A changed strategy requires an explicit recalculation.

The strategy ranks liquid NSE constituents by a weighted six- and twelve-month momentum score with a 21-session skip. It holds up to ten names, weighted by inverse realized volatility, with optional 200-day filters. See [`config.yaml`](config.yaml) for the baseline. The checked-in results are **selected historical simulations** using today's constituent universe, not a prospective record. Data-provider delays, survivorship bias, corporate actions and execution costs can materially change outcomes.

## Local research site

Python 3.12 and Node 22 (for the UI check) are recommended.

```bash
python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m jobs.refresh                    # first refresh; requires market-data access
uvicorn dashboard.app:api --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Without an initial refresh, the site still shows the bundled baseline and clearly marks the current basket as pending. By default a local refresh uses an ignored SQLite file (`var/research.sqlite`). The free hosted site sets `RESEARCH_SNAPSHOT_URL` to the public GitHub raw snapshot URL; this lets it load new snapshots without a redeploy. Do not put broker credentials on the public web process.

The first refresh creates the model basket and sets both forward indices to 100; it does not claim any prior forward returns. Subsequent refreshes mark the previous basket to new closes, then select a new basket after the first recorded close of a new month. They write one atomic snapshot only when all required prices are available. A failed refresh retains the last snapshot and its original price date. The daily graph is a **hypothetical forward model**, not real investor returns: it excludes execution costs, dividends and account constraints. The separate long-run chart remains a historical backtest.

## Free deployment and weekday refresh

The public site can run as a free Python web service on Render: connect this repository's `main` branch, build with `pip install -r requirements.txt`, and start with `uvicorn dashboard.app:api --host 0.0.0.0 --port $PORT --workers 1`. Set `RESEARCH_SNAPSHOT_URL=https://raw.githubusercontent.com/Juiceyyyy/AlphEdge/main/state/current_snapshot.json` on the web service. No database or broker environment variables are needed. The existing project site is at <https://alphedge-web.onrender.com/explore>. Free web instances can sleep and restart; the bundled historical results still load.

[`.github/workflows/daily-refresh.yml`](.github/workflows/daily-refresh.yml) runs `python -m jobs.refresh` at 13:17 UTC (18:47 IST) on weekdays, and can be run manually from GitHub Actions. It commits **only** `state/current_snapshot.json` when a new price date is available. The site fetches the public file from GitHub with a five-minute cache; it does not need a redeploy after each refresh. GitHub can delay or skip scheduled jobs, and neither provider guarantees a fresh market close. Check the Actions run and the `/api/explore` snapshot price date after market days. A holiday leaves the last date in place. If GitHub Raw is temporarily unavailable, the current snapshot can be unavailable until the next fetch. The snapshot contains model target tickers, percentage weights, prices and a hypothetical forward index; it contains no personal account details.

To run the same refresh locally against a tracked snapshot, set `RESEARCH_SNAPSHOT_FILE=state/current_snapshot.json` for the command and commit the resulting public file. Without this variable, local refreshes use an ignored SQLite file (`var/research.sqlite`). Do not set broker keys in GitHub Actions or Render. The first successful refresh creates a basket and starts both forward indices at 100; it does not claim earlier live returns. Later runs mark the previous target basket to a new closing price, then rebalance after the first recorded close of a new month. A failed refresh leaves the last committed snapshot unchanged. The forward series is a **hypothetical model**, excluding actual execution costs, dividends and account constraints.

The web process serves research data. On-demand scenario calculations are bounded to 5–15 holdings, serialized, and cached in-process; public traffic may need rate limits and separate compute. The market-data and universe sources can fail or change. Review their licenses before wider redistribution. No paid resources are provisioned by this repository.

## Connect **your own** Kite account (local only)

This runner is an opt-in reference integration for **NSE cash-and-carry (CNC)**. It supports only a single account on a trusted machine. It is not a multi-user brokerage service. The public web and cron job never import, store or request Kite credentials.

1. Create a Kite Connect app and set a redirect URL in its dashboard. Copy `.env.example` to `.env` locally and set `KITE_API_KEY`, `KITE_API_SECRET`, `MAX_CAPITAL_INR` and `MAX_ORDER_NOTIONAL_INR`. Keep `.env` private. `config.yaml` selects the strategy; account capital is capped separately by the environment variable.
2. Run `python -m broker.connect`, sign in through the printed official Kite URL, and paste the short-lived `request_token` from your configured redirect. The exchange stores today's access token in ignored `var/broker/access_token` with owner-only permissions. Kite tokens expire the next morning and require a fresh login; do not automate credential entry or share a token.
3. If the strategy already owns stocks in the account, create ignored `var/broker/managed_symbols.json` as an array of their NSE trading symbols, for example `["INFY", "TCS"]`. The runner will never sell unrelated holdings. Review this file carefully before a risk-off rebalance.
4. Run `python -m broker.runner plan`. It reads current broker holdings and quotes, computes integer-share target quantities, and writes `var/broker/latest_plan.json`. It never places an order. Review quantities, current funds, taxes, depository authorization, and every proposed buy and sell.
5. To permit an actual order attempt, set `TRADING_ENABLED=true` **locally** and run `python -m broker.runner execute --confirm PLAN_ID` with the exact ID printed by `plan`, within 15 minutes and during the configured market window. The runner journals intent before each order, submits sells before buys, checks the broker's order status, and stops on an unfilled, rejected, ambiguous or moved-price order. An interrupted plan must be reconciled manually against the broker order book before another run. No automatic retries.

The broker may require separate depository authorization before selling shares. Broker order acceptance is not a fill. This adapter has unit checks and documented fail-closed behavior, but **has not been end-to-end tested with a live Kite account**. Start with a very small plan only after reviewing the code, broker terms and current API behavior. Do not schedule live order execution until you have independently tested authentication, holdings, fills, partial fills, funds, holidays and recovery on your own account. Daily research refreshes can run unattended; account access cannot persist past Kite's token expiry without the user's next login.

## Quality checks

```bash
python -m compileall -q alpha_strategy dashboard broker jobs
python -m unittest discover -s tests -p 'test_*.py'
node --check dashboard/explorer.js
node tests/research_ui_smoke.cjs
```

These cover storage replacement, broker planning without orders, default disabled execution, UI rendering and API interactions with mocked market data. They do **not** establish trading profitability, point-in-time validity, live broker compatibility or market-data availability.

## Public repository boundaries

The repository includes source, configuration templates, historical research outputs and a public model snapshot when available. It excludes `.env`, account tokens, local journals, price caches, SQLite databases, logs and private holdings. Check `git status` and run a secret scan before every public push. Keep account runners in each user's private environment; never paste broker keys into issues, screenshots or public deployment variables.

MIT licensed. Educational research; no investment recommendation or guarantee of returns.
