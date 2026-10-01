"""Precompute every research basket from a single completed market snapshot."""
import json
from datetime import datetime, timezone
from pathlib import Path
from alpha_strategy.config import StrategyConfig
from alpha_strategy.data import download_history
from alpha_strategy.universe import get_constituent_universe, to_yahoo_symbol
from dashboard.explorer import _current_candidates
from jobs.build_scenarios import completed_sessions


def build():
    cfg = StrategyConfig.from_yaml('config.yaml')
    universe = get_constituent_universe(cfg.index_universe, cache_dir=Path('cache'),
                                        max_age_days=cfg.universe_refresh_days)
    raw = completed_sessions(download_history(
        [to_yahoo_symbol(s) for s in universe] + [cfg.benchmark_ticker],
        years=2, cache_dir=cfg.data_cache_dir, refresh_days=0))
    baskets = {}
    for trend in (True, False):
        for stock in (True, False):
            for count in range(5,16):
                key=f'{int(trend)}/{int(stock)}/{count}'
                baskets[key]=_current_candidates(trend,stock,count,prepared=raw,universe=universe)
    payload={'computed_at':datetime.now(timezone.utc).isoformat(),
             'price_date':baskets['1/1/10']['date'],'baskets':baskets}
    path=Path('state/holdings_cache.json')
    temp=path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload,allow_nan=False,separators=(',',':'))+'\n')
    temp.replace(path)
    print(f"Cached {len(baskets)} model baskets through {payload['price_date']}")

if __name__=='__main__':
    build()
