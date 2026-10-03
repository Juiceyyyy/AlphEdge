# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Static, cached research assets for the AlphEdge public page."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import FileResponse

from alpha_strategy.config import StrategyConfig
from alpha_strategy.data import download_history
from alpha_strategy.momentum import benchmark_in_uptrend, rank_universe
from alpha_strategy.universe import get_constituent_universe, rank_by_adtv, to_yahoo_symbol

from .app_data import read_json
from .store import read_remote_json

ROOT = Path(__file__).resolve().parent.parent
ASSETS = Path(__file__).resolve().parent
router = APIRouter()
@router.get("/explore", include_in_schema=False)
def page():
    return FileResponse(ASSETS / "explorer.html", media_type="text/html")


@router.get("/explore/styles.css", include_in_schema=False)
def styles():
    return FileResponse(ASSETS / "explorer.css", media_type="text/css")


@router.get("/explore/app.js", include_in_schema=False)
def script():
    return FileResponse(ASSETS / "explorer.js", media_type="application/javascript")


@router.get("/explore/logo.svg", include_in_schema=False)
def logo():
    return FileResponse(ASSETS / "logo.svg", media_type="image/svg+xml")


PUBLIC_STATE = "https://raw.githubusercontent.com/Juiceyyyy/AlphEdge/main/state/"


def cached_asset(name, fallback):
    """Use the newest public committed cache, retaining the bundled version on outage."""
    remote = read_remote_json(PUBLIC_STATE + name)
    return remote if isinstance(remote, dict) and remote else read_json(ROOT / "state" / name, fallback)


@router.get("/api/explore")
def overview():
    with ThreadPoolExecutor(max_workers=3) as pool:
        snapshot_future = pool.submit(cached_asset, "current_snapshot.json", None)
        research_future = pool.submit(cached_asset, "research_cache.json", {})
        holdings_future = pool.submit(cached_asset, "holdings_cache.json", {})
        snapshot = snapshot_future.result()
        research = research_future.result()
        holdings = holdings_future.result()
    return {
        "snapshot": snapshot,
        "research": research,
        "holdings": holdings,
    }


@router.get("/api/explore/scenarios")
def scenarios():
    remote = read_remote_json(PUBLIC_STATE + "scenarios.json")
    if isinstance(remote, dict) and remote.get("variants"):
        return remote
    path = ROOT / "state/scenarios.json"
    if not path.is_file():
        return {"variants": {}}
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "public, max-age=300"})


def _current_candidates(trend_filter: bool, stock_filter: bool, n_hold: int, prepared=None, universe=None,
                        previous=None, risk_off_hold_count=None):
    cfg = StrategyConfig.from_yaml(ROOT / "config.yaml")
    universe = universe if universe is not None else get_constituent_universe(cfg.index_universe,
                                        cache_dir=ROOT / "cache",
                                        max_age_days=cfg.universe_refresh_days)
    symbols = [to_yahoo_symbol(s) for s in universe]
    raw = dict(prepared) if prepared is not None else download_history(
        symbols + [cfg.benchmark_ticker], years=2, cache_dir=ROOT / cfg.data_cache_dir)
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
    retain = min(n_hold, max(0, cfg.risk_off_hold_count if risk_off_hold_count is None
                              else int(risk_off_hold_count)))
    picks = ranked[:n_hold] if risk_on else []
    inverse = [1 / p.vol if pd.notna(p.vol) and p.vol > 0 else 1 / 0.3 for p in picks]
    denominator = sum(inverse)
    positions = [{'ticker': p.ticker, 'weight': inverse[i] / denominator,
                  'price': p.price, 'momentum': p.score} for i, p in enumerate(picks)]
    if not risk_on and previous and retain:
        # Only retain earlier held stocks. No new names or reinvestment in risk-off.
        scores = {p.ticker: p.score for p in ranked}
        former = previous.get('positions', [])
        survivors = sorted(former, key=lambda p: (-scores.get(p['ticker'], float('-inf')), p['ticker']))[:retain]
        values = []
        for p in former:
            df = data.get(p['ticker'])
            if df is None or date not in df.index or not p.get('price'):
                raise ValueError(f"Missing close for prior holding {p['ticker']}")
            values.append(p['weight'] * float(df.loc[date, 'Close']) / p['price'])
        total = (1 - sum(p['weight'] for p in former)) + sum(values)
        by_ticker = {p['ticker']: v for p, v in zip(former, values)}
        positions = [{'ticker': p['ticker'], 'weight': by_ticker[p['ticker']] / total,
                      'price': float(data[p['ticker']].loc[date, 'Close']),
                      'momentum': scores.get(p['ticker'])} for p in survivors]

    return {"date": date.strftime("%Y-%m-%d"), "risk_on": risk_on,
            "benchmark_close": float(bench.loc[date, "Close"]),
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "settings": {"trend_filter": trend_filter, "stock_filter": stock_filter,
                         "n_hold": n_hold},
            "positions": positions,
            "risk_off_hold_count": retain, "method": "Research model target weights using the latest available close. This is not an actual portfolio or investment recommendation."}


