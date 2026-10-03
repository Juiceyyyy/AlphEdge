import assert from 'node:assert/strict';
import test from 'node:test';
import worker, {subscriberPerformance, buildReport} from './telegram.mjs';

const forward = [
  {date: '2026-01-30', model_index: 100, benchmark_index: 100},
  {date: '2026-02-02', model_index: 102, benchmark_index: 101},
  {date: '2026-02-03', model_index: 99, benchmark_index: 103},
  {date: '2026-03-02', model_index: 100, benchmark_index: 104},
];

test('subscriber KPIs exclude earlier history and use equal SIP cash flows', () => {
  const sub = {joined_date: '2026-02-01', capital: 10000, sip: 1000};
  const result = subscriberPerformance(sub, forward);
  assert.equal(result.since, '2026-02-02');
  assert.equal(result.paid, 11000);
  assert.ok(Math.abs(result.model - (10000 * 100 / 102 + 1000)) < 0.001);
  assert.ok(Math.abs(result.nifty - (10000 * 104 / 101 + 1000)) < 0.001);
  assert.ok(result.dd < 0);
});

test('cash signal still explains the ranking without calling it a buy list', () => {
  const snap = {price_date: '2026-03-02', forward};
  const baskets = {baskets: {
    '1/1/10': {date: '2026-03-02', risk_on: false, positions: []},
    '0/1/15': {positions: [{ticker: 'ABC.NS', momentum: .42}]},
  }};
  const {message, target} = buildReport({joined_date: '2026-02-01',
    capital: 10000, sip: 1000, kpis: true}, snap, baskets);
  assert.match(message, /100% cash/);
  assert.match(message, /not all are buys/);
  assert.match(message, /Nifty 50 price index/);
  assert.deepEqual(target.positions, {});
});

test('webhook rejects requests without the Telegram secret', async () => {
  const result = await worker.fetch(new Request('https://bot.example/telegram', {
    method: 'POST', body: '{}', headers: {'content-type': 'application/json'},
  }), {WEBHOOK_SECRET: 'private-secret'});
  assert.equal(result.status, 403);
});

test('valid private /start is acknowledged immediately and stored without logging secrets', async () => {
  const store = new Map();
  const sent = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_url, options) => {
    sent.push(JSON.parse(options.body));
    return Response.json({ok: true, result: {message_id: 1}});
  };
  try {
    const env = {WEBHOOK_SECRET: 'secret', BOT_TOKEN: 'test-token', SUBSCRIBERS: {
      get: async k => store.has(k) ? JSON.parse(store.get(k)) : null,
      put: async (k, v) => store.set(k, v),
    }};
    const response = await worker.fetch(new Request('https://bot.example/telegram', {
      method: 'POST', headers: {'X-Telegram-Bot-Api-Secret-Token': 'secret'},
      body: JSON.stringify({message: {chat: {type: 'private', id: 123},
        text: '/start', date: Date.parse('2026-10-03T12:00:00Z') / 1000}}),
    }), env);
    assert.equal(response.status, 200);
    assert.equal(JSON.parse(store.get('sub:123')).joined_date, '2026-10-03');
    assert.match(sent[0].text, /Subscribed/);
  } finally { globalThis.fetch = originalFetch; }
});
