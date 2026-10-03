# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Build reusable historical scenario paths for instant client-side illustrations."""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from alpha_strategy.backtest_momentum import MomentumConfig, run_momentum_backtest
from alpha_strategy.config import StrategyConfig
from alpha_strategy.data import download_history
from alpha_strategy.universe import get_constituent_universe, to_yahoo_symbol

MAX_HOLDINGS = 15
STRATEGY_ID = "hold-five-v1"


def build_fingerprint():
    """Invalidate saved paths when the strategy implementation or parameters change."""
    digest = hashlib.sha256()
    for name in ("config.yaml", "alpha_strategy/backtest_momentum.py",
                 "alpha_strategy/momentum.py", "jobs/build_scenarios.py"):
        digest.update(Path(name).read_bytes())
    return digest.hexdigest()


def reusable_variants(previous, through, fingerprint):
    if previous.get("strategy_id") != STRATEGY_ID or previous.get("data_through") != through:
        return {}
    variants = previous.get("variants", {})
    if previous.get("build_fingerprint") == fingerprint:
        return variants
    # The previous 5–10 cache predates fingerprints. Its implementation and
    # parameters are unchanged here; reuse those paths for this expansion only.
    legacy_keys = {f"{int(trend)}/{int(stock)}/{count}/{retained if trend else 0}"
                   for trend in (True, False) for stock in (True, False)
                   for count in range(5, 11)
                   for retained in ((0, 5) if trend else (0,))}
    if not previous.get("build_fingerprint") and set(variants) == legacy_keys:
        return variants
    return {}


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
    target = Path(path)
    previous = json.loads(target.read_text()) if target.exists() else {}
    through = data[cfg.benchmark_ticker].index.max().strftime("%Y-%m-%d")
    fingerprint = build_fingerprint()
    variants = dict(reusable_variants(previous, through, fingerprint))
    print(f"Reusing {len(variants)} verified paths through {through}", flush=True)
    for trend in (True, False):
        for stock in (True, False):
            for count in range(5, MAX_HOLDINGS + 1):
                for retained in ((0, min(5, count)) if trend else (0,)):
                    key = f"{int(trend)}/{int(stock)}/{count}/{retained if trend else 0}"
                    if key in variants:
                        continue
                    mc = MomentumConfig(
                        rebalance_freq="M", n_hold=count,
                        lookback_short=cfg.lookback_short, lookback_long=cfg.lookback_long,
                        momentum_skip=cfg.momentum_skip, weight_short=cfg.weight_short,
                        weight_long=cfg.weight_long, weighting=cfg.weighting,
                        vol_window=cfg.vol_window, require_above_ma=stock,
                        long_ma_window=cfg.long_ma_window, use_trend_filter=trend,
                        trend_filter_window=cfg.trend_filter_window,
                        min_momentum=cfg.min_momentum,
                        target_total_exposure=cfg.target_total_exposure,
                        risk_off_hold_count=retained)
                    result = run_momentum_backtest(cfg, years=15, top_n=cfg.top_n_by_adtv,
                        mc=mc, verbose=False, prepared_data=data, prepared_universe=universe)
                    last_signal = next((t['risk_on'] for t in reversed(result.trades)
                                        if t.get('type') == 'rebalance'), True)
                    variants[key] = {"months": monthly_path(result), "kpis": result.kpis(),
                                     "latest": {"date": result.equity_curve.index[-1].strftime('%Y-%m-%d'),
                                                "risk_on": last_signal,
                                                "positions": result.latest_positions}}
                    print(f"Built {key}: {len(variants[key]['months'])} monthly points", flush=True)
    payload = {"strategy_id": STRATEGY_ID, "build_fingerprint": fingerprint,
               "computed_at": datetime.now(timezone.utc).isoformat(),
               "data_through": through,
               "method": "Historical backtests with shared market data and today's constituent universe. Selected model; not independent out-of-sample validation.",
               "variants": variants}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")) + "\n")
    temporary.replace(target)


if __name__ == "__main__":
    build()
