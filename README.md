<p align="center"><img src="hosting/site/logo.svg" width="76" height="76" alt="AlphEdge logo"></p>

# AlphEdge

**Indian equity momentum research with an optional, locally controlled Zerodha Kite order runner.** Explore the [live research dashboard](https://alph-edge.vercel.app/) or clone the project to run your own model. Developed by [Joshua Menezes](https://github.com/Juiceyyyy).

## How it works

AlphEdge ranks liquid NSE stocks by their six- and twelve-month price momentum, skips the most recent month, and sizes positions by inverse volatility. The default monthly research model targets **10 stocks**. When the Nifty 50 closes below its 200-day moving average, the moderate setting retains the strongest **five existing holdings**, sells the rest, and leaves the proceeds in cash. It does not buy replacements until the filter clears. Low risk holds cash during that period; aggressive ignores the market filter. The site lets you compare these settings and 5–15 target holdings using saved historical paths.

The website and Telegram bot show research data. Neither can access a visitor's broker account. The Kite runner is a separate, optional local tool that prepares a reviewable order plan; orders require explicit local authorization. Backtests use a present-day constituent universe and simplified costs, so they are illustrations rather than verified investable returns. Index comparisons use price indices and exclude dividends.

## Get started

Requires Python 3.12 and Git. Run these commands from a terminal:

```bash
git clone https://github.com/Juiceyyyy/AlphEdge.git
cd AlphEdge
python -m venv .venv
source .venv/bin/activate # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m alpha_strategy.cli.momentum --help
python -m alpha_strategy.cli.momentum --years 5
```

Edit [`config.yaml`](config.yaml) to change the universe, target holdings, risk-off retention, filters, sizing, or assumed costs. Market-data downloads require network access; the first backtest can take time. Changing these settings does not change the already published website caches.

To update your local forward snapshot and view the dashboard:

```bash
python -m jobs.refresh
uvicorn dashboard.app:api --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/explore`. To regenerate the historical scenarios and dashboard summaries after a model change, run the following in order:

```bash
python -m jobs.build_scenarios
python -m jobs.build_benchmarks
python -m jobs.build_research_cache
python -m jobs.build_holdings
python -m jobs.refresh
```

These jobs can download substantial historical data. The completed-close snapshot advances only when a new close is available. Historical scenarios and the forward snapshot are separate; a changed strategy version restarts the forward index rather than relabeling earlier returns.

## Optional: connect your Kite account

Use this only on a computer you control. The broker runner handles NSE delivery (CNC) orders, and its default mode does not execute trades.

1. Copy [`.env.example`](.env.example) to `.env`. Set your Kite API key and secret plus positive `MAX_CAPITAL_INR` and `MAX_ORDER_NOTIONAL_INR` limits. `.env` is ignored by Git.
2. Run `python -m broker.connect`, sign in to Kite, and paste the short-lived request token locally. Renew the access token when required.
3. Create `var/broker/managed_symbols.json` with only the symbols this runner may manage, such as `["INFY", "TCS"]`. It must never manage unrelated holdings.
4. For risk-on expansion, record the latest verified earnings release dates in `var/broker/earnings_clearance.json`, such as `{"INFY":"2026-08-15"}`. The default permitted expansion months are March, June, September, and December; set `REBALANCE_MONTHS` locally if needed. Risk-off reductions can be planned outside that gate.
5. Run `python -m broker.runner plan`. Review the plan, account funds, order limits, market close, fees, and broker authorizations.
6. Only if you decide to place those orders, confirm the current Kite API requirements, then set `BROKER_IP_CONFIRMED=true` and `TRADING_ENABLED=true` locally. Run `python -m broker.runner execute --confirm PLAN_ID` during an allowed exchange session within 15 minutes of planning. Reconcile the broker order book and local journal afterward.

The runner has not been validated end to end with a live account. It cannot guarantee fills or unattended access after a token expires. Keep all credentials and personal account data out of public forks.

## Repository layout

| Path | Purpose |
| --- | --- |
| `alpha_strategy/`, `config.yaml` | Signals, universe, backtest, and model settings |
| `broker/`, `.env.example` | Optional local Kite connection and guarded order planner |
| `jobs/`, `dashboard/` | Research cache builders, forward refresh, and local read-only server |
| `state/` | Published example model and benchmark JSON; required by the public dashboard and bot |
| `hosting/` | Optional website assets, Telegram Worker, and deployment instructions |
| `.github/workflows/` | GitHub Actions schedules and validation; GitHub requires this location |

For a private strategy clone, `hosting/` and `.github/workflows/` are optional. Keep `state/` if you want the bundled research snapshots. See [hosting instructions](hosting/README.md) if you maintain a public site or bot. No paid hosting service is required by this repository.

## Research limits and security

The site compares the strategy with the Nifty 50, Nifty Midcap 150, and Nifty Smallcap 250 **price** indices from downloaded close data. The latter two series have shorter available history; unavailable dates remain unavailable rather than being filled with zero returns. The strategy's historical constituent selection is not point-in-time verified. Taxes, brokerage, slippage, dividends, data gaps, and execution may materially change actual results. This project is educational research, not personalized investment advice.

Never commit `.env`, tokens, journals, personal holdings, or local caches. See [SECURITY.md](SECURITY.md) and the [MIT license](LICENSE).
