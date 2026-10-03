# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Cache monthly checkpoints of the two additional Yahoo Finance price indices."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alpha_strategy.data import download_history
from jobs.build_scenarios import completed_sessions

INDICES = {'midcap150': 'NIFTYMIDCAP150.NS',
           'smallcap250': 'NIFTYSMLCAP250.NS'}


def monthly_levels(dates, closes):
    """Use the most recent completed close before each strategy checkpoint."""
    by_day = {day.date().isoformat(): float(value) for day, value in closes.items()
              if value > 0}
    known = sorted(by_day)
    first_month = date.fromisoformat(dates[0]).replace(day=1).isoformat()
    earlier = [day for day in known if day < first_month]
    initial = by_day[earlier[-1]] if earlier else None
    levels = []
    index = 0
    for stamp in dates:
        while index < len(known) and known[index] <= stamp:
            index += 1
        day = known[index - 1] if index else None
        recent = day and (date.fromisoformat(stamp) - date.fromisoformat(day)).days <= 8
        levels.append(by_day[day] if recent else None)
    return initial, levels


def build(path='state/benchmarks.json', scenarios_path='state/scenarios.json'):
    scenarios = json.loads(Path(scenarios_path).read_text())
    dates = [row['date'] for row in scenarios['variants']['1/1/10/5']['months']]
    history = completed_sessions(download_history(list(INDICES.values()), years=15,
                                                 cache_dir='cache/ohlcv'))
    monthly = [{'date': stamp} for stamp in dates]
    initial = {}
    for key, ticker in INDICES.items():
        frame = history.get(ticker)
        if frame is None or frame.empty or 'Close' not in frame:
            raise RuntimeError(f'Index data unavailable for {ticker}; preserving the prior cache')
        close = frame['Close'].dropna()
        if close.empty or close.index.max().date() < date.fromisoformat(scenarios['data_through']) - timedelta(days=12):
            raise RuntimeError(f'Index data stale for {ticker}; preserving the prior cache')
        initial[key], levels = monthly_levels(dates, close)
        if not any(level is not None for level in levels):
            raise RuntimeError(f'No historical overlap for {ticker}')
        for row, level in zip(monthly, levels):
            row[key] = level
        print(f'{ticker}: {close.index.min().date()}–{close.index.max().date()} ({len(close)} closes)', flush=True)
    result = {'source': 'Yahoo Finance delayed price indices via yfinance; dividends excluded',
              'symbols': INDICES, 'strategy_id': scenarios['strategy_id'],
              'data_through': scenarios['data_through'],
              'computed_at': datetime.now(timezone.utc).isoformat(),
              'initial': initial, 'monthly': monthly}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False) + '\n')
    temporary.replace(target)
    print(f'Cached {len(monthly)} index checkpoints through {scenarios["data_through"]}')


if __name__ == '__main__':
    build()
