// SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
// SPDX-License-Identifier: MIT
// Free Cloudflare Worker: instant private commands and scheduled research alerts.
const SOURCE = 'https://raw.githubusercontent.com/Juiceyyyy/AlphEdge/main/state/';
const HELP = `ALPHEDGE · RESEARCH BOT
/start — Subscribe to model updates
/now — Show the latest full report
/settings — View your assumptions
/capital 10000 — Set starting amount (₹)
/sip 5000 — Set monthly contribution (₹)
/kpis on|off — Show or hide performance
/help — Show these commands
/stop — Delete your subscription

Tracks the published 10-stock research model. No broker access or orders.`;

const amount = n => `${n < 0 ? '-' : ''}₹${Math.abs(n).toLocaleString('en-IN', {maximumFractionDigits: 0})}`;
const pct = n => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
const symbol = s => s.replace(/\.NS$/, '');
const key = id => `sub:${id}`;

async function telegram(env, method, data) {
  const response = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(`Telegram ${method} failed (${response.status})`);
  const json = await response.json();
  if (!json.ok) throw new Error(`Telegram ${method} returned an error`);
  return json.result;
}

async function send(env, id, message) {
  if (message.length > 4096) throw new Error('Message exceeds Telegram limit');
  await telegram(env, 'sendMessage', {chat_id: id, text: message,
    disable_web_page_preview: true});
}

async function marketData() {
  const [snap, baskets] = await Promise.all(['current_snapshot.json', 'holdings_cache.json']
    .map(async filename => {
      const response = await fetch(SOURCE + filename, {headers: {'cache-control': 'no-cache'}});
      if (!response.ok) throw new Error('Research data unavailable');
      return response.json();
    }));
  const day = snap.price_date;
  const age = (Date.now() - Date.parse(`${day}T00:00:00Z`)) / 86400000;
  if (baskets.price_date !== day || age < 0 || age > 6 ||
      snap.forward?.at(-1)?.date !== day || baskets.baskets?.['1/1/10']?.date !== day) {
    throw new Error('Research data stale or mismatched');
  }
  return {snap, baskets};
}

export function subscriberPerformance(sub, forward) {
  const start = forward.findIndex(row => row.date >= sub.joined_date);
  if (start < 0 || start >= forward.length - 1) return null;
  let model = sub.capital, nifty = sub.capital, paid = sub.capital;
  let month = forward[start].date.slice(0, 7);
  let peak = forward[start].model_index, niftyPeak = forward[start].benchmark_index;
  let dd = 0, niftyDd = 0;
  for (let i = start + 1; i < forward.length; i++) {
    const prev = forward[i - 1], row = forward[i];
    model *= row.model_index / prev.model_index;
    nifty *= row.benchmark_index / prev.benchmark_index;
    peak = Math.max(peak, row.model_index);
    niftyPeak = Math.max(niftyPeak, row.benchmark_index);
    dd = Math.min(dd, row.model_index / peak - 1);
    niftyDd = Math.min(niftyDd, row.benchmark_index / niftyPeak - 1);
    if (row.date.slice(0, 7) !== month) {
      model += sub.sip; nifty += sub.sip; paid += sub.sip;
      month = row.date.slice(0, 7);
    }
  }
  return {since: forward[start].date, model, nifty, paid,
    modelPct: (model / paid - 1) * 100, niftyPct: (nifty / paid - 1) * 100,
    dd: dd * 100, niftyDd: niftyDd * 100};
}

export function buildReport(sub, snap, baskets) {
  const target = baskets.baskets['1/1/10'];
  const ranking = baskets.baskets['0/1/15'].positions;
  const current = Object.fromEntries(target.positions.map(p => [p.ticker, p.weight]));
  const previous = sub.last_target;
  const old = previous?.positions ?? {};
  const names = [...new Set([...Object.keys(old), ...Object.keys(current)])].sort();
  const changes = names.filter(s => Math.abs((current[s] ?? 0) - (old[s] ?? 0)) >= .005);
  const lines = [
    'ALPHEDGE  |  MODEL REVIEW', `Market close: ${snap.price_date}`,
    'Model: 10 stocks · monthly rebalance · Nifty 200-day filter', '',
    'MARKET & ALLOCATION',
    `Nifty trend: ${target.risk_on ? 'RISK-ON — equity model' : 'RISK-OFF — model in cash'}`,
    `Target: ${target.positions.length} stocks · ${target.positions.length ? 100 : 0}% equity · ${target.positions.length ? 0 : 100}% cash`,
    '', 'TARGET HOLDINGS / WEIGHTS',
    ...(target.positions.length ? target.positions.map((p, i) =>
      `${String(i + 1).padStart(2)}. ${symbol(p.ticker).padEnd(13)} ${(p.weight * 100).toFixed(1)}%`)
      : ['None. The current default model targets cash.']),
    '', 'CHANGES SINCE YOUR LAST REPORT',
    ...(previous ? (changes.length ? changes.map(s =>
      `${symbol(s)}: ${((old[s] ?? 0) * 100).toFixed(1)}% → ${((current[s] ?? 0) * 100).toFixed(1)}%`)
      : ['No target moves of at least 0.5 percentage points.'])
      : ['First report — no earlier target to compare.']),
    '', 'MODEL ACTION',
    target.risk_on ? 'Review these target weights for the next interval.' :
      'Default sell-to-cash model: hold cash until the trend filter clears.',
    'Compare targets with your own holdings. No share quantities or orders are generated.',
  ];
  if (sub.kpis) {
    const p = subscriberPerformance(sub, snap.forward);
    lines.push('', 'SINCE YOU SUBSCRIBED · HYPOTHETICAL');
    if (p) lines.push(
      `From market close: ${p.since}`,
      `Contributed: ${amount(p.paid)}`,
      `AlphEdge model: ${amount(p.model)} | P/L ${amount(p.model - p.paid)} | ${pct(p.modelPct)}`,
      `Nifty 50 price index: ${amount(p.nifty)} | P/L ${amount(p.nifty - p.paid)} | ${pct(p.niftyPct)}`,
      `Difference: ${(p.modelPct - p.niftyPct) >= 0 ? '+' : ''}${(p.modelPct - p.niftyPct).toFixed(2)} percentage points`,
      `Worst drawdown: model ${pct(p.dd)} | Nifty ${pct(p.niftyDd)}`,
    );
    else lines.push('Starts after the next completed market close.');
    lines.push(`Assumptions: ${amount(sub.capital)} initial + ${amount(sub.sip)}/month; excludes trades, fees and tax.`);
  }
  lines.push('', 'UNDERLYING STOCK RANKING · TOP 15',
    'Ranked independently of the market filter; not all are buys.',
    ...ranking.map((p, i) =>
      `${String(i + 1).padStart(2)}. ${symbol(p.ticker).padEnd(13)} score ${p.momentum >= 0 ? '+' : ''}${p.momentum.toFixed(2)}`),
    '', 'Research only. Model values are not broker returns; Nifty excludes dividends.');
  const message = lines.join('\n');
  if (message.length > 4096) throw new Error('Report too long');
  return {message, target: {date: snap.price_date, positions: current, risk_on: target.risk_on}};
}

const settings = sub => `YOUR REPORT SETTINGS\nStarted: ${sub.joined_date}\n` +
  `Initial amount: ${amount(sub.capital)}\nMonthly contribution: ${amount(sub.sip)}\n` +
  `Performance KPIs: ${sub.kpis ? 'on' : 'off'}\n` +
  'Model: published 10-stock forward research index';

async function handle(update, env) {
  const msg = update.message;
  if (msg?.chat?.type !== 'private' || typeof msg.text !== 'string') return;
  const id = String(msg.chat.id);
  const [rawCommand, ...parts] = msg.text.trim().split(/\s+/);
  const command = rawCommand.split('@')[0].toLowerCase();
  const value = parts.join(' ').trim();
  const stored = await env.SUBSCRIBERS.get(key(id), 'json');
  if (command === '/start') {
    const joined = new Date(msg.date * 1000).toISOString().slice(0, 10);
    const sub = stored ?? {joined_date: joined, capital: 10000, sip: 0, kpis: true};
    await env.SUBSCRIBERS.put(key(id), JSON.stringify(sub));
    await send(env, id, `Subscribed. Your comparison starts with the next completed market close.\n\n${HELP}`);
    return;
  }
  if (command === '/stop') {
    await env.SUBSCRIBERS.delete(key(id));
    await send(env, id, 'Subscription removed. Your settings have been deleted.');
    return;
  }
  if (!stored) {
    await send(env, id, 'Send /start to subscribe. No settings are stored until then.');
    return;
  }
  if (command === '/help' || command === '/settings') {
    await send(env, id, command === '/help' ? HELP : settings(stored));
  } else if (command === '/kpis' && ['on', 'off'].includes(value.toLowerCase())) {
    stored.kpis = value.toLowerCase() === 'on';
    await env.SUBSCRIBERS.put(key(id), JSON.stringify(stored));
    await send(env, id, settings(stored));
  } else if (command === '/capital' || command === '/sip') {
    const clean = value.replace(/,/g, '');
    const n = /^\d+$/.test(clean) ? Number(clean) : NaN;
    if (!Number.isSafeInteger(n) || n > 100000000 || (command === '/capital' && n === 0)) {
      await send(env, id, 'Enter a whole rupee amount, for example /capital 10000 or /sip 5000.');
      return;
    }
    stored[command === '/capital' ? 'capital' : 'sip'] = n;
    await env.SUBSCRIBERS.put(key(id), JSON.stringify(stored));
    await send(env, id, `${settings(stored)}\nFigures are recalculated from your start date.`);
  } else if (command === '/now') {
    try {
      const {snap, baskets} = await marketData();
      await send(env, id, buildReport(stored, snap, baskets).message);
    } catch (_error) {
      await send(env, id, 'Market data is incomplete or stale. No report or trade action is available yet.');
    }
  } else await send(env, id, HELP);
}

async function scheduledReport(env) {
  let data;
  try { data = await marketData(); }
  catch (_error) { return; }
  let cursor;
  do {
    const page = await env.SUBSCRIBERS.list({prefix: 'sub:', cursor});
    for (const item of page.keys) {
      const sub = await env.SUBSCRIBERS.get(item.name, 'json');
      if (!sub) continue;
      const old = sub.last_target;
      const now = data.baskets.baskets['1/1/10'];
      if (old?.date?.slice(0, 7) === data.snap.price_date.slice(0, 7) &&
          old.risk_on === now.risk_on) continue;
      const id = item.name.slice(4);
      try {
        const {message, target} = buildReport(sub, data.snap, data.baskets);
        await send(env, id, message);
        sub.last_target = target;
        await env.SUBSCRIBERS.put(item.name, JSON.stringify(sub));
      } catch (_error) {
        // An invalid chat or temporary failure never blocks the other subscribers.
      }
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'POST' && url.pathname === '/telegram') {
      if (!env.WEBHOOK_SECRET ||
          request.headers.get('X-Telegram-Bot-Api-Secret-Token') !== env.WEBHOOK_SECRET)
        return new Response('Forbidden', {status: 403});
      try {
        const update = await request.json();
        await handle(update, env);
        return new Response('OK');
      } catch (_error) {
        return new Response('Retry', {status: 503});
      }
    }
    if (request.method === 'POST' && url.pathname === '/setup' && env.WEBHOOK_SECRET &&
        request.headers.get('X-Setup-Key') === env.WEBHOOK_SECRET) {
      const result = await telegram(env, 'setWebhook', {
        url: `${url.origin}/telegram`, secret_token: env.WEBHOOK_SECRET,
        allowed_updates: ['message'], drop_pending_updates: false,
      });
      return Response.json({webhook_set: result === true});
    }
    if (request.method === 'GET' && url.pathname === '/health')
      return Response.json({service: 'AlphEdge research bot', ready: Boolean(env.SUBSCRIBERS && env.BOT_TOKEN)});
    return new Response('Not found', {status: 404});
  },
  async scheduled(_event, env) { await scheduledReport(env); },
};
