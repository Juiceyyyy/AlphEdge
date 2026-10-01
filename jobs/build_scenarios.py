"""Build reusable historical scenario paths for instant client-side illustrations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from alpha_strategy.backtest_momentum import MomentumConfig, run_momentum_backtest
from alpha_strategy.config import StrategyConfig
from alpha_strategy.data import download_history
from alpha_strategy.universe import get_constituent_universe, to_yahoo_symbol


def monthly_path(result):
    equity = result.equity_curve.dropna().resample("ME").last().dropna()
    benchmark = result.benchmark_curve.reindex(equity.index, method="ffill")
    latest = result.equity_curve.index.max()
    return [{"date": min(date, latest).strftime("%Y-%m-%d"),
             "strategy_return": float(equity.iloc[i] / equity.iloc[i - 1] - 1) if i else 0.0,
             "benchmark_return": float(benchmark.iloc[i] / benchmark.iloc[i - 1] - 1)
             if i and pd.notna(benchmark.iloc[i]) and pd.notna(benchmark.iloc[i - 1])
             and benchmark.iloc[i - 1] else 0.0}
            for i, date in enumerate(equity.index)]


def completed_sessions(data, now=None):
    """Exclude an in-progress India trading day from historical scenarios."""
    local_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Kolkata"))
    if local_now.hour >= 16:
        return data
    today = local_now.date()
    return {symbol: frame[frame.index.date < today]
            for symbol, frame in data.items()}


def build(path="state/scenarios.json"):
    cfg = StrategyConfig.from_yaml("config.yaml")
    cfg.starting_capital = 1_000_000
    universe = get_constituent_universe(cfg.index_universe, cache_dir=Path("cache"),
                                        max_age_days=cfg.universe_refresh_days)
    symbols = [to_yahoo_symbol(s) for s in universe] + [cfg.benchmark_ticker]
    data = completed_sessions(download_history(symbols, years=15,
                                                cache_dir=cfg.data_cache_dir))
    variants = {}
    for trend in (True, False):
        for stock in (True, False):
            for count in (5, 10, 15):
                mc = MomentumConfig(
                    rebalance_freq="M", n_hold=count,
                    lookback_short=cfg.lookback_short, lookback_long=cfg.lookback_long,
                    momentum_skip=cfg.momentum_skip, weight_short=cfg.weight_short,
                    weight_long=cfg.weight_long, weighting=cfg.weighting,
                    vol_window=cfg.vol_window, require_above_ma=stock,
                    long_ma_window=cfg.long_ma_window, use_trend_filter=trend,
                    trend_filter_window=cfg.trend_filter_window,
                    min_momentum=cfg.min_momentum,
                    target_total_exposure=cfg.target_total_exposure)
                result = run_momentum_backtest(cfg, years=15, top_n=cfg.top_n_by_adtv,
                    mc=mc, verbose=False, prepared_data=data, prepared_universe=universe)
                key = f"{int(trend)}/{int(stock)}/{count}"
                variants[key] = {"months": monthly_path(result), "kpis": result.kpis()}
                print(f"Built {key}: {len(variants[key]['months'])} monthly points", flush=True)
    payload = {"computed_at": datetime.now(timezone.utc).isoformat(),
               "data_through": data[cfg.benchmark_ticker].index.max().strftime("%Y-%m-%d"),
               "method": "Historical backtests with shared market data and today's constituent universe. Selected model; not independent out-of-sample validation.",
               "variants": variants}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")) + "\n")
    temporary.replace(target)


if __name__ == "__main__":
    build()
