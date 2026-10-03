# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Materialize annual and three-year views from completed monthly checkpoints.

Completed calendar years are immutable once archived; only the active YTD and
active trailing window change on daily refresh. No web request runs a backtest.
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path


def compounded(months, key):
    value = 1.0
    for item in months:
        value *= 1.0 + float(item[key])
    return (value - 1.0) * 100.0


def summary(months, label=None):
    if not months:
        return None
    years = max((date.fromisoformat(months[-1]['date']) - date.fromisoformat(months[0]['date'])).days / 365.25, 1/12)
    sr = compounded(months, 'strategy_return')
    br = compounded(months, 'benchmark_return')
    growth = 1.0
    peak = 1.0
    worst = 0.0
    for item in months:
        growth *= 1.0 + item['strategy_return']
        peak = max(peak, growth)
        worst = min(worst, (growth / peak - 1) * 100)
    return {'label': label or '', 'start': months[0]['date'], 'end': months[-1]['date'],
            'cagr_pct': ((1+sr/100)**(1/years)-1)*100,
            'bench_cagr_pct': ((1+br/100)**(1/years)-1)*100,
            'max_dd_pct': worst}


def compile_cache(scenarios, previous=None):
    previous = previous or {}
    if previous.get('strategy_id') != scenarios.get('strategy_id'):
        previous = {}  # model changes invalidate frozen annual and window results
    through = date.fromisoformat(scenarios['data_through'])
    archived = dict(previous.get('archived', {}))
    archived_windows = dict(previous.get('archived_windows', {}))
    variants = {}
    for key, variant in scenarios['variants'].items():
        months = variant['months']
        years = sorted({int(m['date'][:4]) for m in months})
        frozen = dict(archived.get(key, {}))
        for year in years:
            if year >= through.year or str(year) in frozen:
                continue
            samples = [m for m in months if m['date'].startswith(str(year))]
            frozen[str(year)] = {'year': year, 'return_pct': compounded(samples,'strategy_return'),
                                 'bench_return_pct': compounded(samples,'benchmark_return')}
        archived[key] = frozen
        ytd = [m for m in months if m['date'].startswith(str(through.year))]
        annual = [frozen[k] for k in sorted(frozen)]
        if ytd:
            annual.append({'year': through.year, 'return_pct': compounded(ytd,'strategy_return'),
                           'bench_return_pct': compounded(ytd,'benchmark_return'), 'active': True,
                           'through': scenarios['data_through']})
        # Fixed calendar windows close at the end of a year. In-progress
        # trailing window is calculated separately from latest 36 checkpoints.
        frozen_windows = dict(archived_windows.get(key, {}))
        for year in years:
            if year + 2 >= through.year or str(year) in frozen_windows:
                continue
            sample = [m for m in months if year <= int(m['date'][:4]) <= year+2]
            if len(sample) >= 30:
                frozen_windows[str(year)] = summary(sample, f'{year}–{year+2}')
        archived_windows[key] = frozen_windows
        windows = [frozen_windows[k] for k in sorted(frozen_windows)]
        active = summary(months[-36:], 'Trailing 36 months · active') if len(months) >= 36 else None
        variants[key] = {'annual': annual, 'windows': windows, 'active_window': active}
    return {'strategy_id': scenarios.get('strategy_id'), 'data_through': scenarios['data_through'], 'archived': archived,
            'archived_windows': archived_windows,
            'variants': variants, 'method': 'Monthly backtest checkpoints. Completed calendar years archived; current year and trailing window refreshed from latest completed close.'}


def build():
    path = Path('state/research_cache.json')
    scenarios = json.loads(Path('state/scenarios.json').read_text())
    previous = json.loads(path.read_text()) if path.exists() else None
    result = compile_cache(scenarios, previous)
    target = path.with_suffix('.json.tmp')
    target.write_text(json.dumps(result, allow_nan=False, separators=(',', ':'))+'\n')
    target.replace(path)
    print(f"Cached {len(result['variants'])} scenario summaries through {result['data_through']}")


if __name__ == '__main__':
    build()
