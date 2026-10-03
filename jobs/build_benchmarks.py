# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Cache NSE Indices price-index closes for static historical comparisons."""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ENDPOINT = 'https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString'
INDICES = {'midcap150': 'NIFTY MIDCAP 150', 'smallcap250': 'NIFTY SMALLCAP 250'}


def fetch_chunk(name: str, start: date, end: date):
    info = "{'name':'%s','startDate':'%s','endDate':'%s','indexName':'%s'}" % (
        name, start.strftime('%d %b %Y'), end.strftime('%d %b %Y'), name)
    body = json.dumps({'cinfo': info}).encode()
    request = Request(ENDPOINT, data=body, headers={
        'Content-Type': 'application/json; charset=utf-8',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': 'https://www.niftyindices.com',
        'Referer': 'https://www.niftyindices.com/reports/historical-data',
        'User-Agent': 'Mozilla/5.0 (compatible; AlphEdgeResearch/1.0)',
    })
    for attempt in range(3):
        try:
            with urlopen(request, timeout=35) as response:
                payload = json.load(response)
            rows = json.loads(payload['d'])
            if not isinstance(rows, list):
                raise ValueError('Unexpected NSE response')
            return rows
        except (OSError, ValueError, KeyError) as exc:
            if attempt == 2:
                raise RuntimeError(f'Could not fetch {name} {start}–{end}') from exc
            time.sleep(2 ** attempt)


def read_closes(rows):
    closes = {}
    for row in rows:
        day = datetime.strptime(row['HistoricalDate'].strip(), '%d %b %Y').date()
        close = float(str(row['CLOSE']).replace(',', ''))
        if close <= 0:
            raise ValueError(f'Invalid index close on {day}')
        closes[day.isoformat()] = close
    return closes


def build(path='state/benchmarks.json', scenarios_path='state/scenarios.json'):
    scenarios = json.loads(Path(scenarios_path).read_text())
    dates = [row['date'] for row in scenarios['variants']['1/1/10/5']['months']]
    target = Path(path)
    prior = json.loads(target.read_text()) if target.exists() else {}
    first = date.fromisoformat(dates[0]) - timedelta(days=40)
    through = date.fromisoformat(scenarios['data_through'])
    series = {}
    for key, name in INDICES.items():
        closes = dict(prior.get('daily', {}).get(key, {}))
        # Recheck the current month and the preceding month on every run.
        cursor = first if not closes else max(first, date.fromisoformat(max(closes)) - timedelta(days=45))
        while cursor <= through:
            end = min(through, cursor + timedelta(days=300))
            rows = fetch_chunk(name, cursor, end)
            if not rows and cursor >= through - timedelta(days=12):
                break
            closes.update(read_closes(rows))
            cursor = end + timedelta(days=1)
            time.sleep(.15)
        if not closes or max(closes) < (through - timedelta(days=12)).isoformat():
            raise RuntimeError(f'{name} index data is stale; preserving the previous cache')
        series[key] = closes
    monthly = []
    for stamp in dates:
        row = {'date': stamp}
        for key in INDICES:
            eligible = [day for day in series[key] if day <= stamp]
            if eligible and (date.fromisoformat(stamp) - date.fromisoformat(max(eligible))).days <= 8:
                row[key] = series[key][max(eligible)]
            else:
                row[key] = None
        monthly.append(row)
    first_month=date.fromisoformat(dates[0]).replace(day=1).isoformat()
    initial={}
    for key in INDICES:
        prior=[day for day in series[key] if day < first_month]
        initial[key]=series[key][max(prior)] if prior else None
    result = {'initial': initial, 'source': 'NSE Indices historical price index (dividends excluded)',
              'source_url': 'https://www.niftyindices.com/reports/historical-data',
              'strategy_id': scenarios['strategy_id'], 'data_through': scenarios['data_through'],
              'computed_at': datetime.now(timezone.utc).isoformat(),
              'monthly': monthly, 'daily': series}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False) + '\n')
    temporary.replace(target)
    print(f'Index history through {through}: ' + ', '.join(f'{key} {len(series[key])} closes' for key in INDICES))


if __name__ == '__main__':
    build()
