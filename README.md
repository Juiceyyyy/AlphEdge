# AlphEdge

**A configurable Indian equity momentum research system with an optional local Zerodha Kite order runner.** Developed by [Joshua Menezes](https://github.com/Juiceyyyy). The [public research site](https://alph-edge.vercel.app/) shows saved backtests, annual and rolling-window comparisons with the Nifty 50, and model holdings at the latest completed close.

The default model ranks liquid NSE stocks using six- and twelve-month momentum with the most recent 21 sessions skipped. It targets ten stocks, sized by inverse volatility. At a monthly review, if the Nifty is below its 200-day average, it **ranks the stocks it already owns by momentum, retains the strongest five and sells the others**. It does not buy replacements or reinvest the cash during risk-off. On a later risk-on review, it resumes the full target basket. Choose a risk appetite: **low** sells all below the Nifty 200-day average, **moderate** keeps five existing holdings and holds the sale proceeds in cash, and **aggressive** ignores that market filter and continues the normal monthly buying rule. Moderate and aggressive maintain separate holdings over time, so moderate's retained five need not appear in aggressive's current basket. The website offers these three presets alongside the 5–15 holding-count slider. A model starting in risk-off with no existing positions stays in cash until risk-on.

The website and bot are research interfaces; neither connects to a visitor's broker. The local runner is an explicit, opt-in order planner for one account. Backtests are selected historical simulations using today's constituent universe, not point-in-time verified investment returns. Historical costs are simplified; actual taxes, fees, dividends, fills, data delays, and selection bias can change outcomes.

## Clone and run the research model

Use Python 3.12 and Git. On Windows PowerShell:

```powershell
git clone https://github.com/Juiceyyyy/AlphEdge.git
cd AlphEdge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m alpha_strategy.cli.momentum --help
```

On macOS/Linux use `source .venv/bin/activate` instead. Edit [`config.yaml`](config.yaml) for your universe, target holdings, `risk_off_hold_count`, moving-average filters, sizing, and cost assumptions. The three published presets are low (trend on, retention zero), moderate (trend on, retention five), and aggressive (trend off). The default is moderate with ten target holdings and five retained on risk-off. Other custom YAML combinations run locally, but the published cached website only includes the three presets. Market-data downloads require network access. The bundled JSON assets are historical research examples, not a live quote source.

To refresh a local forward model and view the research site:

```powershell
python -m jobs.refresh
uvicorn dashboard.app:api --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/explore`. `python -m jobs.refresh` advances only on a new completed close; a strategy-version change resets its forward index to 100 so prior sell-all returns cannot be presented as hold-five returns. To rebuild saved scenarios, annual/window summaries, and current baskets after changing the model:

```powershell
python -m jobs.build_scenarios
python -m jobs.build_research_cache
python -m jobs.build_holdings
```

These runs download a large equity history and can take considerable time. The browser replays precomputed paths without starting a backtest. The selected configuration is not independently walk-forward trained, and historical constituents are not point-in-time verified. The daily forward record starts at its actual first saved snapshot, separately from the retrospective 2026 chart.

## Connect your own Kite account (optional)

The order runner supports NSE cash-and-carry (CNC) on a trusted local computer. It never runs on the public site or GitHub Actions. **Planning is read-only; execution requires separate explicit local settings and a plan ID.** Review the code and broker requirements before authorizing any orders.

1. Copy [`.env.example`](.env.example) to `.env`. Set `KITE_API_KEY`, `KITE_API_SECRET`, `MAX_CAPITAL_INR`, and `MAX_ORDER_NOTIONAL_INR`. Keep `.env` private. Public completed-close references are the default; paid broker quote access is optional, never required by this repository.
2. Run `python -m broker.connect`. Sign in via Kite and paste the short-lived request token locally. Renew the access token when it expires; the project does not store account credentials in a hosted service.
3. Create `var/broker/managed_symbols.json` with **only** the NSE symbols this runner may manage, for example `["INFY","TCS"]`. Unrelated personal holdings are never sold. Set the capital limit high enough for these managed positions.
4. On risk-on reviews, confirm each target's latest actual earnings release in `var/broker/earnings_clearance.json`, for example `{"INFY":"2026-08-15"}`. The default expansion months are March, June, September, and December; change `REBALANCE_MONTHS` locally if needed. A risk-off reduction can be planned outside that quarterly expansion gate and never buys or resizes retained shares.
5. Run `python -m broker.runner plan`. Review the proposed buys/sells, whole-share rounding, limits, available funds, costs, depository authorization, and the latest market close. It will refuse stale data or missing required releases.
6. If you independently decide to execute, confirm your Kite account's current API and static-IP requirements, then set `BROKER_IP_CONFIRMED=true` and `TRADING_ENABLED=true` **locally**. Run `python -m broker.runner execute --confirm PLAN_ID` during the allowed exchange session, within 15 minutes of planning. Reconcile the journal and broker order book after any partial or ambiguous order.

The runner has unit checks but has **not** been end-to-end validated with a live Kite account. Start with a small manually reviewed plan. It cannot guarantee fills, profits, or unattended account access after token expiry.

## Repository map

| Path | Purpose | Needed to run your own local strategy? |
| --- | --- | --- |
| `alpha_strategy/`, `config.yaml` | Research signal and backtest | Yes |
| `broker/`, `.env.example` | Optional local Kite integration | Only if connecting Kite |
| `dashboard/`, `jobs/`, `state/` | Research page, refresh scripts, and published example caches | Only for site or research refresh |
| `site/`, `vercel.json` | Static Vercel export | No |
| `worker/`, `wrangler.toml.example` | Optional Telegram bot on Cloudflare Free | No |
| `.github/workflows/` | Free scheduled public research updates and code checks | No for a local clone |
| `tests/` | Focused safety, cache and UI checks | Recommended when changing logic |

You can remove the optional `site/`, `worker/`, and deployment workflow/config files from **your own fork** if you only run local research or broker plans. Keep the strategy source and any dependencies it imports. [Maintainer deployment notes](docs/MAINTAINER_DEPLOYMENT.md) cover the public website and bot.

## Check changes

```powershell
python -m unittest discover -s tests -p "test_*.py"
node --test worker/telegram.test.mjs
node tests/research_ui_smoke.cjs
```

The tests check logic and safety gates; they do not establish strategy profitability, broker connectivity, or live execution. Never commit `.env`, access tokens, private journals, cache databases, or personal holdings to a public fork. [MIT license](LICENSE).

### Benchmark comparisons

The site compares the saved strategy path with the Nifty 50, Nifty Midcap 150, and Nifty Smallcap 250 price indices. The latter two monthly checkpoints are derived from official [NSE Indices historical price levels](https://www.niftyindices.com/reports/historical-data) by `python -m jobs.build_benchmarks`. The free GitHub Actions scenario-cache job refreshes the data after market close and publishes `state/benchmarks.json` and `site/data/benchmarks.json`. These are price indices, so dividends are excluded; contribution illustrations are hypothetical and do not represent investable index fund returns. Missing or stale index data is never substituted with zero returns.
