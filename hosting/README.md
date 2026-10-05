# Optional public hosting

You do not need this directory to run the local strategy or broker planner. It contains the published static research site and the Telegram notification Worker. No paid hosting feature is required.

## Website

`hosting/site/` is the single source of HTML, CSS, JavaScript, branding, and fallback JSON for the public dashboard. The root [`vercel.json`](../vercel.json) points Vercel at this folder; it stays at the root because Vercel discovers it there. The live site is https://alph-edge.vercel.app/.

`state/` at the repository root is the canonical public research cache. GitHub Actions refreshes it after the Indian market close and copies matching JSON to `hosting/site/data/` as a static fallback. The site prefers the latest public GitHub JSON and uses those bundled copies during an outage. `.github/workflows/` must remain at the repository root for GitHub to execute the schedules. The daily workflow updates the forward model; the scenario workflow builds historical paths, three index series, annual and rolling-window summaries, and current target baskets. Scheduled runs may be delayed or fail when market-data sources are unavailable. Do not present an older snapshot as a current quote.

After changing the model, rebuild the scenarios and summaries described in the root README before publishing. The forward model is versioned and resets on a strategy change; older sell-all returns cannot become hold-five returns by relabeling them. Finished years are archived only within the same model version.

## Telegram Worker

`hosting/telegram/worker.mjs` reads the same public snapshot and sends formatted model updates. Cloudflare Workers Free handles the webhook and an optional hourly cron; KV stores subscriber preferences. The bot has no broker access and does not place trades. Subscriber-since forward KPIs are available only for the published default 10-stock, keep-five model. Other supported settings show target baskets without assigning the default return series to them.

1. Create a bot with @BotFather and a Cloudflare Workers Free account. Keep the bot token private.
2. From `hosting/telegram/`, run `npx wrangler login`, copy `wrangler.toml.example` to ignored `wrangler.toml`, and run `npx wrangler kv namespace create SUBSCRIBERS`. Enter the namespace ID in `wrangler.toml`.
3. Run `npx wrangler deploy`. Store the bot token with `npx wrangler secret put BOT_TOKEN`. Generate a separate random secret and store it with `npx wrangler secret put WEBHOOK_SECRET`.
4. Check `https://YOUR-WORKER.workers.dev/health` for `ready: true`. POST to `https://YOUR-WORKER.workers.dev/setup` with the `X-Setup-Key` header set to your webhook secret. Do this locally without putting the secret in a public command history or log.
5. Send `/start` to your bot, complete onboarding, and check `/now` and `/settings`. Reusing the same KV namespace preserves subscriber settings across Worker updates.

Do not commit `wrangler.toml`, tokens, subscriber records, or broker credentials. The public site and bot are research interfaces, not account automation.
