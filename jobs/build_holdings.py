# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Publish target baskets from the same backtests as the scenario cache."""
import json
from datetime import datetime, timezone
from pathlib import Path


def build():
    scenarios = json.loads(Path('state/scenarios.json').read_text())
    if scenarios.get('strategy_id') != 'hold-five-v1':
        raise RuntimeError('Historical scenarios have not been regenerated for hold-five-v1')
    date = scenarios['data_through']
    baskets = {}
    for key, variant in scenarios['variants'].items():
        latest = variant['latest']
        if latest['date'] != date:
            raise RuntimeError(f'Current basket {key} differs from scenario price date')
        baskets[key] = {**latest, 'settings': {'key': key},
                        'method': 'Simulated target after the latest close; weights include residual cash. Pending fills would occur on the next session.'}
    payload = {'strategy_id': 'hold-five-v1',
               'computed_at': datetime.now(timezone.utc).isoformat(),
               'price_date': date, 'baskets': baskets}
    path = Path('state/holdings_cache.json')
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, allow_nan=False, separators=(',', ':')) + '\n')
    temp.replace(path)
    print(f"Cached {len(baskets)} model baskets through {date}")


if __name__ == '__main__':
    build()
