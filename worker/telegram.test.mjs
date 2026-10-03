import assert from 'node:assert/strict';
import test from 'node:test';
import worker, {subscriberPerformance, buildReport} from './telegram.mjs';

const forward = [
  {date: '2026-01-30', model_index: 100, benchmark_index: 100},
  {date: '2026-02-02', model_index: 102, benchmark_index: 101},
  {date: '2026-02-03', model_index: 99, benchmark_index: 103},
  {date: '2026-03-02', model_index: 100, benchmark_index: 104},
];
const fixtures = (risk_on = false) => ({
  snap: {price_date: '2026-03-02', forward},
  baskets: {baskets: {
    '1/1/10/5': {date: '2026-03-02', risk_on,
      positions: risk_on ? [{ticker: 'ABC.NS', weight: 1}] : []},
    '0/1/15': {positions: [{ticker: 'ABC.NS', momentum: .42}]},
  }},
});
const date = Date.parse('2026-10-03T12:00:00Z') / 1000;
function mockBot() {
  const store = new Map(), sent = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_url, options) => {
    sent.push(JSON.parse(options.body));
    return Response.json({ok: true, result: {message_id: 1}});
  };
  const env = {WEBHOOK_SECRET: 'secret', BOT_TOKEN: 'test-token', SUBSCRIBERS: {
    get: async k => store.has(k) ? JSON.parse(store.get(k)) : null,
    put: async (k, v) => store.set(k, v),
    delete: async k => store.delete(k),
    list: async () => ({keys: [...store.keys()].map(name => ({name})), list_complete: true}),
  }};
  const command = async text => {
    const response = await worker.fetch(new Request('https://bot.example/telegram', {
      method: 'POST', headers: {'X-Telegram-Bot-Api-Secret-Token': 'secret'},
      body: JSON.stringify({message: {chat: {type: 'private', id: 123}, text, date}}),
    }), env);
    assert.equal(response.status, 200, `command ${text}`);
    return sent.at(-1);
  };
  return {store, sent, env, command, restore: () => { globalThis.fetch = originalFetch; }};
}

test('subscriber KPIs exclude earlier history and use equal SIP cash flows', () => {
  const sub = {joined_date: '2026-02-01', capital: 10000, sip: 1000};
  const result = subscriberPerformance(sub, forward);
  assert.equal(result.since, '2026-02-02');
  assert.equal(result.paid, 11000);
  assert.ok(Math.abs(result.model - (10000 * 100 / 102 + 1000)) < 0.001);
  assert.ok(Math.abs(result.nifty - (10000 * 104 / 101 + 1000)) < 0.001);
  assert.ok(result.dd < 0);
});

test('cash model has readable sections, a small index chart, and no buy instruction', () => {
  const {snap, baskets} = fixtures();
  const {message, target} = buildReport({joined_date: '2026-02-01',
    capital: 10000, sip: 1000, kpis: true}, snap, baskets);
  assert.match(message, /100%/);
  assert.match(message, /<b>05  SINCE YOU STARTED/);
  assert.match(message, /NIFTY 50/);
  assert.match(message, /RECENT INDEX PATH/);
  assert.match(message, /retains|Keep up to/);
  assert.deepEqual(target.positions, {});
});

test('equity rows escape ticker text before Telegram HTML parsing', () => {
  const {snap, baskets} = fixtures(true);
  baskets.baskets['1/1/10/5'].positions[0].ticker = 'A&B.NS';
  const {message} = buildReport({joined_date: '2026-02-01',
    capital: 10000, sip: 0, kpis: false}, snap, baskets);
  assert.match(message, /A&amp;B/);
  assert.match(message, /100\.0%/);
});

test('webhook rejects requests without the Telegram secret', async () => {
  const result = await worker.fetch(new Request('https://bot.example/telegram', {
    method: 'POST', body: '{}', headers: {'content-type': 'application/json'},
  }), {WEBHOOK_SECRET: 'private-secret'});
  assert.equal(result.status, 403);
});

test('new user completes amount, SIP, and paper-tracking onboarding', async () => {
  const bot = mockBot();
  try {
    assert.match((await bot.command('/start')).text, /INITIAL AMOUNT/);
    assert.equal(bot.sent.at(-1).parse_mode, 'HTML');
    assert.match((await bot.command('5000')).text, /MONTHLY SIP/);
    assert.match((await bot.command('500')).text, /CHOOSE YOUR TRACKING/);
    assert.match((await bot.command('3')).text, /PAPER TRACKING STARTED/);
    const saved = JSON.parse(bot.store.get('sub:123'));
    assert.deepEqual([saved.capital, saved.sip, saved.mode, saved.status, saved.joined_date],
      [5000, 500, 'paper', 'active', '2026-10-03']);
    assert.match((await bot.command('/start')).text, /WELCOME BACK/);
  } finally { bot.restore(); }
});

test('waiting user receives no scheduled alert, then start activates tracking', async () => {
  const bot = mockBot();
  try {
    await bot.command('/start');
    assert.match((await bot.command('0')).text, /above zero/);
    await bot.command('10000'); await bot.command('0');
    assert.match((await bot.command('2')).text, /No reports are sent while waiting/);
    const sentBefore = bot.sent.length;
    await bot.env.SUBSCRIBERS.list();
    // A scheduled call is safe even when snapshot fetch fails; waiting is never active.
    assert.equal(JSON.parse(bot.store.get('sub:123')).status, 'waiting');
    assert.equal(bot.sent.length, sentBefore);
    assert.match((await bot.command('1')).text, /TRACKING STARTED/);
    assert.equal(JSON.parse(bot.store.get('sub:123')).mode, 'live');
    await bot.command('/stop');
    assert.equal(bot.store.has('sub:123'), false);
  } finally { bot.restore(); }
});

test('existing active subscribers retain their original start date', async () => {
  const bot = mockBot();
  try {
    bot.store.set('sub:123', JSON.stringify({joined_date: '2026-10-01', capital: 10000, sip: 0, kpis: true}));
    assert.match((await bot.command('/start')).text, /WELCOME BACK/);
    assert.equal(JSON.parse(bot.store.get('sub:123')).joined_date, '2026-10-01');
  } finally { bot.restore(); }
});

test('onboarding buttons choose paper mode without requiring an ambiguous yes', async () => {
  const bot = mockBot();
  try {
    await bot.command('/start'); await bot.command('10000');
    const prompt = await bot.command('1000');
    assert.equal(prompt.reply_markup.inline_keyboard[1][0].text, 'Paper tracking');
    const response = await worker.fetch(new Request('https://bot.example/telegram', {
      method: 'POST', headers: {'X-Telegram-Bot-Api-Secret-Token': 'secret'},
      body: JSON.stringify({callback_query: {id: 'callback1', data: 'begin:paper',
        from: {id: 123}, message: {chat: {type: 'private', id: 123}}}}),
    }), bot.env);
    assert.equal(response.status, 200);
    assert.equal(JSON.parse(bot.store.get('sub:123')).mode, 'paper');
  } finally { bot.restore(); }
});

test('custom model targets are selected without attributing default forward KPIs', () => {
  const {snap, baskets} = fixtures();
  baskets.baskets['1/1/8/3'] = {date: '2026-03-02', risk_on: false,
    positions: [{ticker: 'ABC.NS', weight: .36}]};
  const {message} = buildReport({joined_date: '2026-02-01', capital: 10000,
    sip: 1000, kpis: true, holdings: 8, retain: 3}, snap, baskets);
  assert.match(message, /8-stock monthly model/);
  assert.match(message, /36%/);
  assert.match(message, /only for the published default model/);
  assert.doesNotMatch(message, /Model P\/L/);
});
