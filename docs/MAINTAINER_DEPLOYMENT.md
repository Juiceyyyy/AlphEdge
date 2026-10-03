# Optional public deployment

These instructions are for maintainers who want the public research site and private Telegram bot. A local clone or broker account does not need either deployment.

## Static Vercel site and free GitHub Actions caches

`dashboard/` contains the site source. Run `python -m jobs.export_site` to update `site/`, the static Vercel output; `vercel.json` points Vercel there. The existing public site is https://alph-edge.vercel.app/. The site loads public GitHub JSON and falls back to the packaged copies. Historical scenarios, the immutable completed-year cache, and daily holdings are built by `.github/workflows/scenario-cache.yml` after the close. `.github/workflows/daily-refresh.yml` updates the separate forward model snapshot. Both schedules use free GitHub Actions; market-data downloads may fail or be delayed. The client requires matching `hold-five-v1` identifiers, preventing old sell-all returns from appearing under the new strategy. On a model change, rebuild all caches and export the static fallbacks before treating the site as current. The active YTD and trailing window are rebuilt; completed years are archived only within the same model version.

## Cloudflare Free Telegram Worker

`worker/telegram.mjs` handles private webhook commands in near real time. The optional hourly Cloudflare Free cron reads the latest completed GitHub snapshot and sends alerts after the first updated close of the month or a trend-state change. KV stores subscriber settings. Telegram has no custom text-color API; the bot uses supported HTML formatting and inline buttons. The bot does not place trades, access brokerage credentials, or calculate custom-model daily subscriber returns. Subscriber-since forward KPIs are shown only for the default 10-stock/keep-five model; custom settings show target baskets without attributing the default series to them.

1. Create a Telegram bot with @BotFather, keep its token private, and create a Cloudflare Workers Free account.
2. From the repository root, run `npx wrangler login`, copy `wrangler.toml.example` to ignored `wrangler.toml`, and run `npx wrangler kv namespace create SUBSCRIBERS`. Put its namespace ID in `wrangler.toml`.
3. Run `npx wrangler deploy`. Store the BotFather token via `npx wrangler secret put BOT_TOKEN`. Generate a separate secret with `python -c "import secrets; print(secrets.token_urlsafe(32))"`; save it privately and run `npx wrangler secret put WEBHOOK_SECRET`.
4. Verify `https://YOUR-WORKER.workers.dev/health` reports `ready: true`. In PowerShell use `$key = Read-Host 'WEBHOOK_SECRET'`, `$url = 'https://YOUR-WORKER.workers.dev'`, and `Invoke-RestMethod -Method Post -Uri "$url/setup" -Headers @{'X-Setup-Key'=$key}`. Confirm `webhook_set: true`, then `Remove-Variable key`.
5. Send `/start` and complete onboarding; use `/now` and `/settings` to verify. Existing subscribers on the same KV namespace retain their start date after normal Worker updates.

Never paste secrets into repository files, issues, shell command arguments, or screenshots. Do not reactivate a GitHub Actions polling bot while this webhook is registered. The published snapshots are research data, not personalized trading instructions.
