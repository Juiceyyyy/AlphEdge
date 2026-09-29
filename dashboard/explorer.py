"""Interactive research page for AlphEdge.

The saved annual results power the fast initial view. Strategy changes run the
actual backtest on demand; they never masquerade as precomputed results.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import time

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from alpha_strategy.backtest_momentum import MomentumConfig, run_momentum_backtest
from alpha_strategy.config import StrategyConfig
from alpha_strategy.data import download_history
from alpha_strategy.momentum import benchmark_in_uptrend, rank_universe
from alpha_strategy.universe import get_constituent_universe, rank_by_adtv, to_yahoo_symbol

from .app_data import read_json
from .store import read_snapshot

ROOT = Path(__file__).resolve().parent.parent
ASSETS = Path(__file__).resolve().parent
router = APIRouter()
_calculation_lock = asyncio.Lock()


class Scenario(BaseModel):
    trend_filter: bool = True
    stock_filter: bool = True
    n_hold: int = Field(default=10, ge=5, le=15)


@router.get("/explore", include_in_schema=False)
def page():
    return FileResponse(ASSETS / "explorer.html", media_type="text/html")


@router.get("/explore/styles.css", include_in_schema=False)
def styles():
    return FileResponse(ASSETS / "explorer.css", media_type="text/css")


@router.get("/explore/app.js", include_in_schema=False)
def script():
    return FileResponse(ASSETS / "explorer.js", media_type="application/javascript")


@router.get("/api/explore")
def overview():
    winner = read_json(ROOT / "state/winner_max_sharpe.json", {})
    wf = read_json(ROOT / "state/walk_forward.json", {})
    snapshot = read_snapshot()
    return {
        "snapshot": snapshot,
        "backtest": {"kpis": winner.get("kpis", {}), "yearly": winner.get("yearly", [])},
        "windows": wf.get("windows_3y", []),
        "method": "Saved historical backtest. Annual points are available before recalculation.",
    }


def _run_scenario(trend_filter: bool, stock_filter: bool, n_hold: int):
    cfg = StrategyConfig.from_yaml(ROOT / "config.yaml")
    # Keep historical engine capital comparable to the saved 1M backtest.
    # The visitor's deposit is replayed afterward from percentage returns.
    cfg.starting_capital = 1_000_000
    mc = MomentumConfig(
        rebalance_freq="M", n_hold=n_hold, lookback_short=cfg.lookback_short,
        lookback_long=cfg.lookback_long, momentum_skip=cfg.momentum_skip,
        weight_short=cfg.weight_short, weight_long=cfg.weight_long,
        weighting=cfg.weighting, vol_window=cfg.vol_window,
        require_above_ma=stock_filter, long_ma_window=cfg.long_ma_window,
        use_trend_filter=trend_filter, trend_filter_window=cfg.trend_filter_window,
        min_momentum=cfg.min_momentum, target_total_exposure=cfg.target_total_exposure,
    )
    result = run_momentum_backtest(cfg, years=15, top_n=cfg.top_n_by_adtv,
                                   mc=mc, verbose=False)
    raw_equity = result.equity_curve.dropna()
    latest_price_date = raw_equity.index.max()
    equity = raw_equity.resample("ME").last().dropna()
    if len(equity) < 12:
        raise ValueError("Insufficient historical data for this scenario")
    benchmark = result.benchmark_curve
    benchmark = benchmark.reindex(equity.index, method="ffill") if benchmark is not None else None
    months = []
    for i, (dt, value) in enumerate(equity.items()):
        months.append({
            "date": min(dt, latest_price_date).strftime("%Y-%m-%d"),
            "strategy_return": 0 if i == 0 else float(value / equity.iloc[i-1] - 1),
            "benchmark_return": (0 if i == 0 or benchmark is None or
                pd.isna(benchmark.iloc[i]) or pd.isna(benchmark.iloc[i-1]) or
                benchmark.iloc[i-1] == 0 else
                float(benchmark.iloc[i] / benchmark.iloc[i-1] - 1)),
        })
    return {"kpis": result.kpis(), "months": months,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "data_through": latest_price_date.strftime("%Y-%m-%d"),
            "method": "Recomputed from historical prices; monthly return replay for investment illustration."}


@lru_cache(maxsize=24)
def _cached_scenario(trend_filter: bool, stock_filter: bool, n_hold: int, cache_day: int):
    return _run_scenario(trend_filter, stock_filter, n_hold)


@router.post("/api/explore/scenario")
async def scenario(request: Scenario):
    if _calculation_lock.locked():
        raise HTTPException(status_code=429, detail="A calculation is already running; try again shortly.")
    try:
        async with _calculation_lock:
            return await run_in_threadpool(_cached_scenario, request.trend_filter,
                                           request.stock_filter, request.n_hold,
                                           int(time.time() // 86400))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Backtest unavailable: {type(exc).__name__}") from exc


def _current_candidates(trend_filter: bool, stock_filter: bool, n_hold: int):
    cfg = StrategyConfig.from_yaml(ROOT / "config.yaml")
    universe = get_constituent_universe(cfg.index_universe,
                                        cache_dir=ROOT / "cache",
                                        max_age_days=cfg.universe_refresh_days)
    symbols = [to_yahoo_symbol(s) for s in universe]
    raw = download_history(symbols + [cfg.benchmark_ticker],
                           years=2, cache_dir=ROOT / cfg.data_cache_dir)
    bench = raw.pop(cfg.benchmark_ticker, None)
    if bench is None or bench.empty:
        raise ValueError("Benchmark prices unavailable")
    date = pd.Timestamp(bench.index.max())
    data = {s: df[df.index <= date] for s, df in raw.items()
            if df is not None and not df.empty and pd.Timestamp(df.index.max()) == date}
    liquid = rank_by_adtv(data, cfg.adtv_lookback_days, cfg.top_n_by_adtv)
    ranked = rank_universe({s: data[s] for s in liquid if s in data}, date,
                           lookbacks=(cfg.lookback_short, cfg.lookback_long),
                           weights=(cfg.weight_short, cfg.weight_long),
                           skip=cfg.momentum_skip,
                           long_ma_window=cfg.long_ma_window,
                           vol_window=cfg.vol_window,
                           min_score=cfg.min_momentum,
                           require_above_ma=stock_filter)
    risk_on = not trend_filter or benchmark_in_uptrend(
        bench["Close"], date, cfg.trend_filter_window)
    picks = ranked[:n_hold] if risk_on else []
    inverse = [1 / p.vol if pd.notna(p.vol) and p.vol > 0 else 1 / 0.3 for p in picks]
    denominator = sum(inverse)
    return {"date": date.strftime("%Y-%m-%d"), "risk_on": risk_on,
            "benchmark_close": float(bench.loc[date, "Close"]),
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "settings": {"trend_filter": trend_filter, "stock_filter": stock_filter,
                         "n_hold": n_hold},
            "positions": [
                {"ticker": p.ticker, "weight": inverse[i] / denominator,
                 "price": p.price, "momentum": p.score}
                for i, p in enumerate(picks)
            ], "method": "Research model target weights using the latest available close. This is not an actual portfolio or investment recommendation."}


@lru_cache(maxsize=48)
def _cached_candidates(trend_filter: bool, stock_filter: bool, n_hold: int, quarter_hour: int):
    return _current_candidates(trend_filter, stock_filter, n_hold)


@router.post("/api/explore/candidates")
async def candidates(request: Scenario):
    if _calculation_lock.locked():
        raise HTTPException(status_code=429, detail="A calculation is already running; try again shortly.")
    try:
        async with _calculation_lock:
            return await run_in_threadpool(_cached_candidates, request.trend_filter,
                                           request.stock_filter, request.n_hold,
                                           int(time.time() // 900))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Current candidates unavailable: {type(exc).__name__}") from exc

