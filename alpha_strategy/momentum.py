# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Cross-sectional momentum scoring (Jegadeesh-Titman style).

For each ticker on each rebalance date:
  - Compute 6-month return: r6 = price[t-21] / price[t-126] - 1
  - Compute 12-month return: r12 = price[t-21] / price[t-252] - 1
    (skip the last 21 trading days to avoid short-term reversal noise)
  - momentum_score = w6 * r6 + w12 * r12
  - filter: price > 200-DMA AND momentum_score > 0

Cash-out regime gate: if benchmark < benchmark_200dma, hold no risk.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd


def trailing_return(prices: pd.Series, lookback: int, skip: int = 21) -> float:
    """Return from t-lookback to t-skip (skip avoids short-term reversal)."""
    if prices is None or len(prices) < lookback + 1:
        return float("nan")
    end = prices.iloc[-1 - skip] if skip > 0 and len(prices) > skip else prices.iloc[-1]
    start = prices.iloc[-1 - lookback]
    if start <= 0 or not np.isfinite(start) or not np.isfinite(end):
        return float("nan")
    return float(end / start - 1.0)


def momentum_score(prices: pd.Series,
                   lookbacks: tuple[int, ...] = (126, 252),
                   weights: tuple[float, ...] = (0.5, 0.5),
                   skip: int = 21) -> float:
    rets = []
    for lb in lookbacks:
        r = trailing_return(prices, lb, skip)
        rets.append(r)
    if any(not np.isfinite(r) for r in rets):
        return float("nan")
    return float(sum(w * r for w, r in zip(weights, rets)))


def realized_vol(prices: pd.Series, window: int = 63) -> float:
    """Annualized vol from daily log returns over `window` bars."""
    if prices is None or len(prices) < window + 1:
        return float("nan")
    rets = np.log(prices / prices.shift(1)).dropna().tail(window)
    if rets.empty or rets.std() == 0:
        return float("nan")
    return float(rets.std() * np.sqrt(252))


def above_long_ma(prices: pd.Series, window: int = 200) -> bool:
    if prices is None or len(prices) < window:
        return False
    ma = prices.tail(window).mean()
    return float(prices.iloc[-1]) > float(ma)


@dataclass
class MomentumPick:
    ticker: str
    score: float
    price: float
    vol: float        # annualized; for inverse-vol sizing
    r6: float
    r12: float


def rank_universe(price_data: dict[str, pd.DataFrame],
                  as_of: pd.Timestamp,
                  lookbacks: tuple[int, ...] = (126, 252),
                  weights: tuple[float, ...] = (0.5, 0.5),
                  skip: int = 21,
                  long_ma_window: int = 200,
                  vol_window: int = 63,
                  min_score: float = 0.0,
                  require_above_ma: bool = True) -> list[MomentumPick]:
    """Compute momentum rank for all tickers as of `as_of`. Returns sorted descending."""
    out: list[MomentumPick] = []
    for sym, df in price_data.items():
        if df is None or df.empty:
            continue
        sub = df[df.index <= as_of]
        if len(sub) < max(lookbacks) + skip + 5:
            continue
        close = sub["Close"]
        sc = momentum_score(close, lookbacks, weights, skip)
        if not np.isfinite(sc):
            continue
        if sc < min_score:
            continue
        if require_above_ma and not above_long_ma(close, long_ma_window):
            continue
        v = realized_vol(close, vol_window)
        if not np.isfinite(v) or v <= 0:
            v = float("nan")
        out.append(MomentumPick(
            ticker=sym, score=sc, price=float(close.iloc[-1]),
            vol=v,
            r6=trailing_return(close, lookbacks[0], skip) if len(lookbacks) >= 1 else float("nan"),
            r12=trailing_return(close, lookbacks[1], skip) if len(lookbacks) >= 2 else float("nan"),
        ))
    out.sort(key=lambda x: x.score, reverse=True)
    return out


def benchmark_in_uptrend(benchmark_close: pd.Series | None,
                         as_of: pd.Timestamp,
                         window: int = 200) -> bool:
    """True if benchmark > 200-DMA at as_of. None benchmark -> always True (no filter)."""
    if benchmark_close is None or benchmark_close.empty:
        return True
    sub = benchmark_close[benchmark_close.index <= as_of]
    if len(sub) < window:
        return True
    return float(sub.iloc[-1]) > float(sub.tail(window).mean())

