// SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
// SPDX-License-Identifier: MIT
// Free Cloudflare Worker: private onboarding, instant commands, scheduled research alerts.
const SOURCE = 'https://raw.githubusercontent.com/Juiceyyyy/AlphEdge/main/state/';
const HELP = `<b>ALPHEDGE  /  RESEARCH BOT</b>\n\n/start — Set up or resume tracking\n/now — Latest model report\n/settings — Your assumptions and tracking mode\n/capital 10000 — Initial amount (₹)\n/sip 5000 — Monthly amount (₹)\n/kpis on|off — Toggle performance section\n/help — Commands\n/stop — Delete your subscription\n\n<i>Research model only. No broker access or orders.</i>`;
const amount = n => `${n < 0 ? '-' : ''}₹${Math.abs(n).toLocaleString('en-IN', {maximumFractionDigits: 0})}`;
const pct = n => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
const escape = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const symbol = s => String(s).replace(/\.NS$/, '');
const key = id => `sub:${id}`;
const dateInIndia = seconds => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(seconds * 1000));
const active = sub => sub && (sub.status === 'active' || (!sub.status && sub.joined_date));
const bar = (share, width = 10) => '▰'.repeat(Math.round(share * width)) + '▱'.repeat(width - Math.round(share * width));
function sparkline(rows, field) {
  const sampled = rows.slice(-24);
  if (sampled.length < 2) return '';
  const values = sampled.map(r => r[field]);
  const lo = Math.min(...values), hi = Math.max(...values);
  const glyphs = '▁▂▃▄▅▆▇█';
  return values.map(v => glyphs[hi === lo ? 3 : Math.round((v - lo) / (hi - lo) * 7)]).join('');
}

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
  await telegram(env, 'sendMessage', {chat_id: id, text: message, parse_mode: 'HTML',
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
  const equity = target.positions.reduce((sum, p) => sum + p.weight, 0);
  const rows = target.positions.map((p, i) =>
    `${String(i + 1).padStart(2)} ${escape(symbol(p.ticker)).padEnd(15)} ${String((p.weight * 100).toFixed(1) + '%').padStart(6)}`);
  const lines = [
    '<b>ALPHEDGE  /  MODEL REVIEW</b>',
    `<i>Close ${escape(snap.price_date)} · 10-stock monthly model</i>`, '',
    '<b>01  MARKET STATE</b>',
    `<b>${target.risk_on ? 'RISK ON' : 'RISK OFF'}</b>  ·  Nifty 200-day filter`,
    `Equity  ${bar(equity)} ${(equity * 100).toFixed(0)}%`,
    `Cash    ${bar(1 - equity)} ${((1 - equity) * 100).toFixed(0)}%`, '',
    '<b>02  TARGET HOLDINGS</b>',
    ...(rows.length ? [`<pre>${rows.join('\n')}</pre>`] : ['<i>No current equity targets. The default model targets cash.</i>']),
    '', '<b>03  TARGET CHANGES</b>',
    ...(previous ? (changes.length ? changes.map(s =>
      `${escape(symbol(s))}  ${((old[s] ?? 0) * 100).toFixed(1)}% → ${((current[s] ?? 0) * 100).toFixed(1)}%`)
      : ['No weight changes of at least 0.5 percentage points.'])
      : ['First report; no earlier target to compare.']),
    '', '<b>04  MODEL NOTE</b>',
    target.risk_on ? 'Review target weights for the next interval.' :
      'Default model targets cash until the trend filter clears.',
    '<i>Compare with your own holdings; no orders or share quantities are generated.</i>',
  ];
  if (sub.kpis) {
    const p = subscriberPerformance(sub, snap.forward);
    lines.push('', '<b>05  SINCE YOU STARTED · HYPOTHETICAL</b>');
    if (p) {
      lines.push(`Since ${p.since} · contributed ${amount(p.paid)}`,
        `<pre>ALPHEDGE  ${amount(p.model).padStart(11)}  ${pct(p.modelPct).padStart(8)}\nNIFTY 50   ${amount(p.nifty).padStart(11)}  ${pct(p.niftyPct).padStart(8)}</pre>`,
        `Model P/L ${amount(p.model - p.paid)} · Nifty P/L ${amount(p.nifty - p.paid)}`,
        `Difference <b>${(p.modelPct - p.niftyPct) >= 0 ? '+' : ''}${(p.modelPct - p.niftyPct).toFixed(2)} percentage points</b>`,
        `Index drawdown: model ${pct(p.dd)} · Nifty ${pct(p.niftyDd)}`);
      const path = snap.forward.filter(r => r.date >= p.since);
      if (path.length >= 2) lines.push('<b>RECENT INDEX PATH</b> <i>(last 24 closes; independent scales, excludes SIP)</i>',
        `<pre>Model  ${sparkline(path, 'model_index')}\nNifty  ${sparkline(path, 'benchmark_index')}</pre>`);
    } else lines.push('Starts after the next completed market close.');
    lines.push(`<i>${amount(sub.capital)} initial + ${amount(sub.sip)}/month; excludes fees, taxes and execution.</i>`);
  }
  lines.push('', '<b>06  UNDERLYING STOCK RANKING</b>',
    '<i>Top 15 momentum signals; rankings are not buy instructions.</i>',
    `<pre>${ranking.map((p, i) =>
      `${String(i + 1).padStart(2)} ${escape(symbol(p.ticker)).padEnd(15)} ${p.momentum >= 0 ? '+' : ''}${p.momentum.toFixed(2)}`).join('\n')}</pre>`,
    '<i>Research only · hypothetical index values, not broker returns · Nifty price index excludes dividends.</i>');
  const message = lines.join('\n');
  if (message.length > 4096) throw new Error('Report too long');
  return {message, target: {date: snap.price_date, positions: current, risk_on: target.risk_on}};
}

const settings = sub => `<b>ALPHEDGE  /  YOUR SETTINGS</b>\n` +
  `Tracking: <b>${active(sub) ? (sub.mode === 'paper' ? 'paper research' : 'live assumption') : 'waiting to start'}</b>\n` +
  `Start: ${sub.joined_date ?? 'not started'}\n` +
  `Initial amount: ${amount(sub.capital)}\nMonthly SIP: ${amount(sub.sip)}\n` +
  `Performance KPIs: ${sub.kpis ? 'on' : 'off'}\n` +
  '<i>Published 10-stock forward research index; not your actual account.</i>';
const question = stage => stage === 'capital'
  ? '<b>01 / 03 · INITIAL AMOUNT</b>\nWhat amount would you like to track initially? Reply with whole rupees, for example <code>10000</code>.'
  : stage === 'sip'
    ? '<b>02 / 03 · MONTHLY SIP</b>\nHow much will you add each month? Reply with whole rupees, or <code>0</code> for no SIP.'
    : stage === 'intent'
      ? '<b>03 / 03 · WHEN TO BEGIN</b>\nReply <code>start</code> if you are starting now, or <code>later</code> if you are not investing yet. You can track a paper scenario instead by replying <code>yes</code>.'
      : '<b>SETUP SAVED</b>\nReply <code>start</code> when you begin investing, or <code>yes</code> to track a paper scenario from today. No reports are sent while waiting.';
function parseAmount(value, allowZero) {
  const clean = value.replace(/,/g, '');
  const n = /^\d+$/.test(clean) ? Number(clean) : NaN;
  return Number.isSafeInteger(n) && n <= 100000000 && (allowZero || n > 0) ? n : null;
}
async function save(env, id, sub) { await env.SUBSCRIBERS.put(key(id), JSON.stringify(sub)); }

async function handle(update, env) {
  const msg = update.message;
  if (msg?.chat?.type !== 'private' || typeof msg.text !== 'string') return;
  const id = String(msg.chat.id);
  const [rawCommand, ...parts] = msg.text.trim().split(/\s+/);
  const command = rawCommand.split('@')[0].toLowerCase();
  const value = parts.join(' ').trim();
  const stored = await env.SUBSCRIBERS.get(key(id), 'json');
  if (command === '/stop') {
    await env.SUBSCRIBERS.delete(key(id));
    await send(env, id, 'Your subscription and settings were deleted. Send /start to set up again.');
    return;
  }
  if (command === '/start') {
    if (stored?.stage === 'waiting') {
      stored.stage = null; stored.status = 'active'; stored.mode = 'live';
      stored.joined_date = dateInIndia(msg.date);
      await save(env, id, stored);
      await send(env, id, `<b>TRACKING STARTED</b>\n${settings(stored)}\n\nUse /now for the current model report.`);
    } else if (stored && active(stored)) {
      await send(env, id, `<b>WELCOME BACK</b>\n${settings(stored)}\n\nUse /now for the latest model review.`);
    } else if (stored) {
      await send(env, id, question(stored.stage));
    } else {
      await save(env, id, {stage: 'capital', status: 'setup', kpis: true});
      await send(env, id, `<b>WELCOME TO ALPHEDGE</b>\n<i>Follow the published Indian equity research model against the Nifty 50. No broker connection is required.</i>\n\n${question('capital')}`);
    }
    return;
  }
  if (command === '/help') { await send(env, id, HELP); return; }
  if (!stored) { await send(env, id, 'Send /start to set up your private research tracker.'); return; }
  if (command === '/settings') {
    await send(env, id, stored.stage && stored.stage !== 'waiting' ? question(stored.stage) : settings(stored));
    return;
  }
  if (stored.stage === 'capital' || stored.stage === 'sip') {
    const field = stored.stage;
    const n = parseAmount(msg.text.trim(), field === 'sip');
    if (n === null) { await send(env, id, `Enter a whole rupee amount ${field === 'capital' ? 'above zero' : 'of zero or more'}, up to ₹10,00,00,000.`); return; }
    stored[field] = n; stored.stage = field === 'capital' ? 'sip' : 'intent';
    await save(env, id, stored);
    await send(env, id, question(stored.stage));
    return;
  }
  if (stored.stage === 'intent' || stored.stage === 'waiting') {
    if (command === 'start' || command === 'yes') {
      stored.stage = null; stored.status = 'active'; stored.mode = command === 'yes' ? 'paper' : 'live';
      stored.joined_date = dateInIndia(msg.date);
      await save(env, id, stored);
      await send(env, id, `<b>${stored.mode === 'paper' ? 'PAPER TRACKING STARTED' : 'TRACKING STARTED'}</b>\n${settings(stored)}\n\nUse /now for the latest model report. Forward KPIs begin after the next completed close.`);
    } else if (command === 'later') {
      stored.stage = 'waiting'; stored.status = 'waiting';
      await save(env, id, stored);
      await send(env, id, question('waiting'));
    } else await send(env, id, question(stored.stage));
    return;
  }
  if (command === '/kpis' && ['on', 'off'].includes(value.toLowerCase())) {
    stored.kpis = value.toLowerCase() === 'on';
    await save(env, id, stored); await send(env, id, settings(stored));
  } else if (command === '/capital' || command === '/sip') {
    const field = command.slice(1);
    const n = parseAmount(value, field === 'sip');
    if (n === null) { await send(env, id, 'Enter whole rupees, for example /capital 10000 or /sip 5000.'); return; }
    stored[field] = n;
    await save(env, id, stored);
    await send(env, id, `${settings(stored)}\nFigures are recalculated from your tracking start date.`);
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
      if (!active(sub)) continue;
      const old = sub.last_target;
      const now = data.baskets.baskets['1/1/10'];
      if (old?.date?.slice(0, 7) === data.snap.price_date.slice(0, 7) &&
          old.risk_on === now.risk_on) continue;
      const id = item.name.slice(4);
      try {
        const {message, target} = buildReport(sub, data.snap, data.baskets);
        await send(env, id, message);
        sub.last_target = target;
        await save(env, id, sub);
      } catch (_error) {
        // One invalid chat or temporary failure never blocks other subscribers.
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
