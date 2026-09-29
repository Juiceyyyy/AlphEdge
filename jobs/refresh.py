"""Refresh the public, forward-only research model after market close."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from alpha_strategy.config import StrategyConfig
from alpha_strategy.data import download_history
from dashboard.explorer import _current_candidates
from dashboard.store import read_snapshot, write_snapshot


def latest_close(data, symbol, date):
    frame = data.get(symbol)
    if frame is None or frame.empty or date not in frame.index:
        raise RuntimeError(f"No closing price for {symbol} on {date.date()}; snapshot unchanged")
    value = float(frame.loc[date, "Close"])
    if value <= 0:
        raise RuntimeError(f"Invalid closing price for {symbol}")
    return value


def refresh():
    cfg = StrategyConfig.from_yaml("config.yaml")
    previous = read_snapshot()
    if previous is None:
        basket = _current_candidates(cfg.use_trend_filter, cfg.require_above_ma, cfg.n_hold)
        snapshot = {"generated_at": datetime.now(timezone.utc).isoformat(),
                    "price_date": basket["date"], "basket": basket,
                    "forward": [{"date": basket["date"], "model_index": 100.0,
                                 "benchmark_index": 100.0, "model_return_pct": 0.0}]}
        write_snapshot(snapshot)
        print(f"Forward model initialized at {basket['date']}; no prior performance implied")
        return

    before = previous["basket"]
    symbols = [p["ticker"] for p in before["positions"]]
    data = download_history([cfg.benchmark_ticker] + symbols, years=1,
                            cache_dir=Path(cfg.data_cache_dir), refresh_days=0)
    benchmark = data.get(cfg.benchmark_ticker)
    if benchmark is None or benchmark.empty:
        raise RuntimeError("Benchmark data unavailable; snapshot unchanged")
    date = benchmark.index.max()
    date_string = date.strftime("%Y-%m-%d")
    if date_string <= previous["price_date"]:
        print(f"No new market close after {previous['price_date']}")
        return

    values = []
    for position in before["positions"]:
        close = latest_close(data, position["ticker"], date)
        values.append((position, close, position["weight"] * close / position["price"]))
    gross = sum(v[2] for v in values) if values else 1.0
    model_return = gross - 1.0
    benchmark_close = latest_close(data, cfg.benchmark_ticker, date)
    benchmark_return = benchmark_close / before["benchmark_close"] - 1.0
    last = previous["forward"][-1]
    forward = previous["forward"] + [{"date": date_string,
        "model_index": last["model_index"] * (1 + model_return),
        "benchmark_index": last["benchmark_index"] * (1 + benchmark_return),
        "model_return_pct": model_return * 100}]

    if date_string[:7] != before["date"][:7]:
        # New basket is established after this close, affecting subsequent returns.
        basket = _current_candidates(cfg.use_trend_filter, cfg.require_above_ma, cfg.n_hold)
        if basket["date"] != date_string:
            raise RuntimeError("Rebalance data dates disagree; snapshot unchanged")
    else:
        basket = {**before, "date": date_string, "benchmark_close": benchmark_close,
                  "positions": [{**p, "price": close, "weight": value / gross}
                                for p, close, value in values]}
    snapshot = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "price_date": date_string, "basket": basket, "forward": forward}
    write_snapshot(snapshot)
    print(f"Forward model updated through {date_string}; {len(basket['positions'])} target holdings")


if __name__ == "__main__":
    refresh()
