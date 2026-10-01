# AlphEdge

An Indian-equity momentum research site with a weekday forward model record and an optional **self-hosted** Zerodha Kite account runner. [Explore the public site](https://alphedge-web.onrender.com/explore). It shows historical simulations and the stocks the model would target using the latest available close. It never connects to a visitor's brokerage account or displays real account balances. The highlighted **Connect broker** link on the site leads to the local setup instructions below; it does not connect an account in the browser.

## What you can inspect

- Historical strategy and Nifty 50 results, annual returns, three-year windows, drawdown, and risk-adjusted metrics.
- A lump-sum and monthly-contribution illustration based on saved historical results. The daily scenario cache supplies monthly backtest checkpoints.
- Current model stocks and target percentage weights, with the latest price date. A risk-off signal can produce a 100% cash target. A separate forward model record starts at 100 on its first observation. The January–September 2026 timeline before that observation is a retrospective reconstruction.
- Instant switches for the Nifty and individual-stock 200-day moving-average filters, plus saved 5–15-stock scenarios. Amount, monthly contribution and date range replay locally without a backtest request.

The strategy ranks liquid NSE constituents by a weighted six- and twelve-month momentum score with a 21-session skip. The default holds up to ten names, weighted by inverse realized volatility, with optional 200-day filters. See [`config.yaml`](config.yaml) for the baseline. The checked-in results are **selected historical simulations** using today's constituent universe, not a prospective record. Data-provider delays, survivorship bias, corporate actions and execution costs can materially change outcomes.

## Local research site

Python 3.12 and Node 22 (for the UI check) are recommended.

```bash
python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m jobs.refresh                    # first refresh; requires market-data access
uvicorn dashboard.app:api --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` (it redirects to `/explore`). Without an initial refresh, the site still shows the bundled baseline and clearly marks a missing current basket as pending. By default a local refresh uses an ignored SQLite file (`var/research.sqlite`). The hosted Render API reads public JSON from GitHub and retains bundled copies for outages. Do not put broker credentials on the public web process.

The first refresh creates the model basket and sets both forward indices to 100; it does not claim any prior forward returns. Subsequent refreshes mark the previous basket to new closes, then select a new basket after the first recorded close of a new month. They write one atomic snapshot only when all required prices are available. A failed refresh retains the last snapshot and its original price date. The daily graph is a **hypothetical forward model**, not real investor returns: it excludes execution costs, dividends and account constraints. The separate long-run chart remains a historical backtest.

## Free static hosting and daily caches

The public deployment currently runs the read-only FastAPI site on Render's free web service. `site/` and `vercel.json` are a static export prepared for Vercel; this repository does not imply that a Vercel deployment is live. Run `python -m jobs.export_site` after editing `dashboard/` or generated `state/` files. The static browser checks public GitHub JSON every 15 minutes while open and falls back to its deployed copies when the network source fails. The Render API refreshes its remote cache on a five-minute window. The two GitHub Actions schedules refresh the public snapshot and saved scenario, annual, window and holdings caches after the Indian close; scheduled jobs and market data can be delayed. A market holiday leaves the previous completed price date visible. There is no always-on trading worker.

The 2026 timeline is a reconstructed historical simulation from January, **not** a prospective performance record. The separately saved forward observations begin on the first actual daily snapshot and are never spliced onto earlier reconstructed values. The published backtest uses monthly rebalancing; the optional local broker policy below uses quarterly reviews and has **no claimed backtested return**. The window review reuses the historically selected configuration; it is not an independent out-of-sample walk-forward training exercise. Historical constituent membership and execution can differ.

## Connect **your own** Kite account (local only)

This runner is an opt-in reference integration for **NSE cash-and-carry (CNC)**. It supports only a single account on a trusted machine. It is not a multi-user brokerage service. The public web and cron job never import, store or request Kite credentials.

1. Create a free Kite Personal app if you only need portfolio and order APIs. The optional broker quote mode requires market-data permission, which may be a paid tier. Copy `.env.example` to `.env` locally and set `KITE_API_KEY`, `KITE_API_SECRET`, `MAX_CAPITAL_INR`, and `MAX_ORDER_NOTIONAL_INR`. Keep the public site and GitHub Actions free of account keys.
2. Run `python -m broker.connect` on your own computer, sign in through the official Kite URL, and paste the short-lived request token. The local access token expires the next morning and must be renewed by you. Never publish it.
3. If the runner already manages shares in your account, create `var/broker/managed_symbols.json` listing only those NSE symbols. Unrelated account holdings are never sold by this runner.
4. The default rebalance review months are March, June, September and December, after the preceding reporting season. Create `var/broker/earnings_clearance.json` with the **verified actual release date** for every target ticker, for example `{"INFY":"2026-08-15"}`. The runner requires each date within the preceding 120 days and refuses a second completed rebalance in the same quarter. This is a manual check, not an automated earnings feed. Adjust `REBALANCE_MONTHS` locally if your review schedule differs.
5. Run `python -m broker.runner plan` after verifying the releases. By default it uses free public completed-close prices; it rejects missing or stale data and estimates whole-share targets. The planned limit prices cap buys and set a floor for sales, but a resting order may not fill. `BROKER_QUOTE_SOURCE=broker` is optional when your broker API permits LTP quotes. Review capital, all proposed orders, corporate actions, taxes, and depository authorization.
6. Confirm your broker account’s current API order IP requirements and register the required static IP. Set `BROKER_IP_CONFIRMED=true` and `TRADING_ENABLED=true` **only on your own machine** and run `python -m broker.runner execute --confirm PLAN_ID` within 15 minutes and the trading session. It journals intent before each order, checks funds and final order status, and stops on an incomplete or ambiguous result. Reconcile the broker order book manually before a new run.

Confirm current Kite order API and registered-IP requirements with the broker before enabling execution; a laptop connection without an approved fixed IP may not be able to execute. Neither the public Render site nor the static export sends orders. The broker may require separate depository authorization before selling shares. Broker order acceptance is not a fill. This adapter has unit checks and documented fail-closed behavior, but **has not been end-to-end tested with a live Kite account**. Start with a very small plan only after reviewing the code, broker terms and current API behavior. Do not schedule live order execution until you have independently tested authentication, holdings, fills, partial fills, funds, holidays and recovery on your own account. Daily research refreshes can run unattended; account access cannot persist past Kite's token expiry without the user's next login.

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
