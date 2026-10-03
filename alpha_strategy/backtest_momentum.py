# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Monthly-rebalanced cross-sectional momentum backtest.

Master calendar = benchmark trading days. On the first trading day of every
month: refresh ADTV-ranked universe (no leakage), rank by momentum, apply
filters, generate target weights, execute fills at the next bar's open.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import logging
import math

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .data import download_history
from .universe import get_constituent_universe, to_yahoo_symbol, rank_by_adtv
from .momentum import rank_universe, benchmark_in_uptrend, MomentumPick

log = logging.getLogger("alpha_strategy.momentum_backtest")


@dataclass
class MomentumConfig:
    """Tuneable knobs for the momentum strategy."""
    rebalance_freq: str = "M"           # 'M' = monthly, 'W-MON' = weekly, 'D' = daily check
    n_hold: int = 10                    # number of stocks held when fully invested
    risk_off_hold_count: int = 5       # strongest existing holdings kept below Nifty MA
    lookback_short: int = 126           # ~6 months
    lookback_long: int = 252            # ~12 months
    momentum_skip: int = 21             # ~1 month skip
    weight_short: float = 0.3
    weight_long: float = 0.7
    long_ma_window: int = 200
    require_above_ma: bool = True
    min_momentum: float = 0.0
    use_trend_filter: bool = True
    trend_filter_window: int = 200
    weighting: str = "inverse_vol"      # 'equal' | 'inverse_vol'
    vol_window: int = 63
    target_total_exposure: float = 1.0
    # Hysteresis band: hold a position while it's in top-(n_hold + replacement_band).
    # 0 = strict (rebalance every check); >0 = sticky / lower turnover.
    replacement_band: int = 0
    # Only re-weight unchanged holdings if total target-vs-current weight drift > this.
    weight_drift_threshold: float = 0.0


def _resolve_momentum_cfg(cfg: StrategyConfig) -> MomentumConfig:
    mc = MomentumConfig()
    for f in mc.__dataclass_fields__:
        if hasattr(cfg, f):
            setattr(mc, f, getattr(cfg, f))
    return mc


def _rebalance_dates(all_dates: pd.DatetimeIndex, freq: str) -> pd.DatetimeIndex:
    """First trading day of each period (month/week), or every day if 'D'."""
    if all_dates.empty:
        return all_dates
    f = freq.upper()
    if f == "D":
        return all_dates.unique().sort_values()
    s = pd.Series(0, index=all_dates)
    if f == "M":
        marks = s.groupby([all_dates.year, all_dates.month]).transform("idxmin")
        firsts = s.index[s.index == marks]
    elif f.startswith("W"):
        marks = s.resample("W-MON").first().dropna().index
        firsts = pd.DatetimeIndex([all_dates[all_dates >= d][0]
                                    for d in marks if (all_dates >= d).any()])
    else:
        firsts = all_dates
    return pd.DatetimeIndex(firsts).unique().sort_values()


def _target_weights(picks: list[MomentumPick],
                    n_hold: int,
                    weighting: str,
                    target_exposure: float) -> dict[str, float]:
    sel = picks[:n_hold]
    if not sel:
        return {}
    if weighting == "inverse_vol":
        invs = []
        for p in sel:
            v = p.vol if (p.vol and np.isfinite(p.vol) and p.vol > 0) else 0.30
            invs.append(1.0 / v)
        s = sum(invs)
        if s <= 0:
            return {}
        weights = {p.ticker: target_exposure * (iv / s) for p, iv in zip(sel, invs)}
    else:
        w = target_exposure / len(sel)
        weights = {p.ticker: w for p in sel}
    return weights


@dataclass
class MomentumResult:
    equity_curve: pd.Series
    benchmark_curve: pd.Series | None
    trades: list[dict[str, Any]]
    holdings_history: list[dict[str, Any]]
    config: dict[str, Any]
    latest_positions: list[dict[str, Any]] = field(default_factory=list)

    def kpis(self) -> dict[str, Any]:
        eq = self.equity_curve.dropna()
        if eq.empty:
            return {}
        n_years = max((eq.index[-1] - eq.index[0]).days / 365.25, 0.01)
        total_ret = eq.iloc[-1] / eq.iloc[0] - 1.0
        cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1.0
        rolling_max = eq.cummax()
        dd = (eq / rolling_max - 1.0)
        max_dd = dd.min()
        rets = eq.pct_change().dropna()
        sharpe = (rets.mean() / rets.std() * math.sqrt(252)) if rets.std() > 0 else 0.0
        calmar = (cagr / abs(max_dd)) if max_dd < 0 else 0.0

        out = {
            "start": str(eq.index[0].date()),
            "end": str(eq.index[-1].date()),
            "starting_capital": float(eq.iloc[0]),
            "ending_capital": float(eq.iloc[-1]),
            "total_return_pct": float(total_ret * 100),
            "cagr_pct": float(cagr * 100),
            "max_drawdown_pct": float(max_dd * 100),
            "sharpe": float(sharpe),
            "calmar": float(calmar),
            "n_rebalances": sum(1 for t in self.trades if t.get("type") == "rebalance"),
            "n_fills": sum(1 for t in self.trades if t.get("type") == "fill"),
        }
        if self.benchmark_curve is not None and not self.benchmark_curve.empty:
            b = self.benchmark_curve.reindex(eq.index).ffill().bfill()
            b_total = b.iloc[-1] / b.iloc[0] - 1.0
            b_cagr = (b.iloc[-1] / b.iloc[0]) ** (1 / n_years) - 1.0
            out["benchmark_total_return_pct"] = float(b_total * 100)
            out["benchmark_cagr_pct"] = float(b_cagr * 100)
            out["alpha_pct_per_yr"] = float((cagr - b_cagr) * 100)

            # Active years beating benchmark
            df = pd.DataFrame({"eq": eq, "bench": b}).dropna()
            df["year"] = df.index.year
            yr = df.groupby("year").agg(eq=("eq", lambda x: x.iloc[-1] / x.iloc[0] - 1),
                                          b=("bench", lambda x: x.iloc[-1] / x.iloc[0] - 1))
            beats = int((yr["eq"] > yr["b"]).sum())
            out["years_beating_benchmark"] = beats
            out["years_total"] = int(len(yr))
        return out

    def yearly_returns(self) -> pd.DataFrame:
        eq = self.equity_curve.dropna()
        if eq.empty:
            return pd.DataFrame()
        df = eq.to_frame("equity")
        df["year"] = df.index.year
        yearly = df.groupby("year")["equity"].agg(["first", "last"])
        yearly["return_pct"] = (yearly["last"] / yearly["first"] - 1) * 100
        if self.benchmark_curve is not None and not self.benchmark_curve.empty:
            b = self.benchmark_curve.reindex(eq.index).ffill().bfill()
            b_df = b.to_frame("bench")
            b_df["year"] = b_df.index.year
            b_yearly = b_df.groupby("year")["bench"].agg(["first", "last"])
            yearly["bench_return_pct"] = (b_yearly["last"] / b_yearly["first"] - 1) * 100
            yearly["alpha_pct"] = yearly["return_pct"] - yearly["bench_return_pct"]
        return yearly.reset_index()


def run_momentum_backtest(cfg: StrategyConfig,
                          years: int | None = None,
                          top_n: int | None = None,
                          mc: MomentumConfig | None = None,
                          verbose: bool = True,
                          prepared_data: dict[str, pd.DataFrame] | None = None,
                          prepared_universe: list[str] | None = None) -> MomentumResult:
    yrs = years or cfg.data_lookback_years
    top = top_n or cfg.top_n_by_adtv
    if mc is None:
        mc = _resolve_momentum_cfg(cfg)

    nse = prepared_universe if prepared_universe is not None else get_constituent_universe(
        cfg.index_universe, cache_dir=Path("cache"), max_age_days=cfg.universe_refresh_days)
    yahoo = [to_yahoo_symbol(s) for s in nse]
    if verbose:
        log.info("Momentum BT universe: %d candidates, top-%d by ADTV", len(yahoo), top)

    raw = dict(prepared_data) if prepared_data is not None else download_history(
        yahoo + [cfg.benchmark_ticker], years=yrs, cache_dir=cfg.data_cache_dir)
    bench_df = raw.pop(cfg.benchmark_ticker, None)
    bench_close = bench_df["Close"] if bench_df is not None and not bench_df.empty else None

    # Master calendar = benchmark days when available, else union
    if bench_close is not None and not bench_close.empty:
        all_dates = bench_close.index
    else:
        all_dates = pd.DatetimeIndex(sorted(set().union(*[d.index for d in raw.values()])))
    # Warm-up cutoff = max lookback + skip
    warmup = mc.lookback_long + mc.momentum_skip + 30
    if len(all_dates) <= warmup:
        raise RuntimeError("Not enough data for momentum backtest")
    all_dates = all_dates[warmup:]

    rebalance_set = set(_rebalance_dates(all_dates, mc.rebalance_freq))
    if verbose:
        log.info("Calendar: %s -> %s (%d bars, %d rebalances)",
                 all_dates[0].date(), all_dates[-1].date(),
                 len(all_dates), len(rebalance_set))

    cash = float(cfg.starting_capital)
    holdings: dict[str, dict[str, float]] = {}    # ticker -> {qty, avg_price}
    pending_rebalance: dict[str, float] | None = None
    pending_hold_only = False
    trades: list[dict[str, Any]] = []
    holdings_history: list[dict[str, Any]] = []
    equity_curve: list[tuple[pd.Timestamp, float]] = []

    last_universe_refresh: pd.Timestamp | None = None
    current_universe: list[str] = []

    for i, dt in enumerate(all_dates):
        # Refresh ADTV universe periodically
        if (last_universe_refresh is None or
                (dt - last_universe_refresh).days >= cfg.universe_refresh_days):
            adtv_in: dict[str, pd.DataFrame] = {}
            for sym, df in raw.items():
                sub = df[df.index <= dt]
                if len(sub) >= 30:
                    adtv_in[sym] = sub
            current_universe = rank_by_adtv(adtv_in,
                                            lookback_days=cfg.adtv_lookback_days,
                                            top_n=top)
            last_universe_refresh = dt

        # Step 1: execute pending rebalance at TODAY's open
        if pending_rebalance is not None:
            target_weights = pending_rebalance
            hold_only = pending_hold_only
            pending_rebalance = None
            pending_hold_only = False
            # Compute equity using today's open for everything we hold
            equity = cash
            for sym, h in holdings.items():
                df = raw.get(sym)
                if df is not None and dt in df.index:
                    px = float(df.loc[dt, "Open"])
                    equity += h["qty"] * px
                else:
                    equity += h["qty"] * h["avg_price"]
            target_value = {sym: w * equity for sym, w in target_weights.items()}

            # Close positions not in target
            for sym in list(holdings.keys()):
                if sym not in target_weights:
                    df = raw.get(sym)
                    if df is None or dt not in df.index:
                        continue
                    px = float(df.loc[dt, "Open"])
                    slip = px * (cfg.slippage_bps / 10000.0)
                    fill = px - slip
                    qty = holdings[sym]["qty"]
                    proceeds = fill * qty
                    commission = proceeds * (cfg.commission_bps / 10000.0)
                    cash += proceeds - commission
                    pnl = (fill - holdings[sym]["avg_price"]) * qty
                    trades.append({
                        "type": "fill", "side": "sell", "ticker": sym,
                        "date": dt.strftime("%Y-%m-%d"), "qty": qty,
                        "price": round(fill, 4), "pnl": round(pnl, 2),
                    })
                    del holdings[sym]

            # Adjust positions to target value (sell partials before buys to free cash)
            adjustments = []
            for sym, tv in target_value.items():
                if hold_only and sym in holdings:
                    continue  # do not resize retained shares in risk-off months
                df = raw.get(sym)
                if df is None or dt not in df.index:
                    continue
                px = float(df.loc[dt, "Open"])
                if px <= 0:
                    continue
                target_qty = int(math.floor(tv / px))
                cur_qty = int(holdings.get(sym, {}).get("qty", 0))
                delta = target_qty - cur_qty
                if delta == 0:
                    continue
                adjustments.append((sym, delta, px))
            adjustments.sort(key=lambda x: x[1])  # sells first

            for sym, delta, px in adjustments:
                if delta < 0:
                    qty = -delta
                    slip = px * (cfg.slippage_bps / 10000.0)
                    fill = px - slip
                    proceeds = fill * qty
                    commission = proceeds * (cfg.commission_bps / 10000.0)
                    cash += proceeds - commission
                    cur = holdings[sym]
                    pnl = (fill - cur["avg_price"]) * qty
                    cur["qty"] -= qty
                    if cur["qty"] <= 0:
                        del holdings[sym]
                    trades.append({
                        "type": "fill", "side": "sell", "ticker": sym,
                        "date": dt.strftime("%Y-%m-%d"), "qty": qty,
                        "price": round(fill, 4), "pnl": round(pnl, 2),
                    })
                else:  # buy
                    qty = delta
                    slip = px * (cfg.slippage_bps / 10000.0)
                    fill = px + slip
                    cost = fill * qty
                    commission = cost * (cfg.commission_bps / 10000.0)
                    if cost + commission > cash:
                        # scale down to what cash allows
                        max_qty = int(math.floor((cash * 0.999) / (fill * (1 + cfg.commission_bps / 10000.0))))
                        if max_qty <= 0:
                            continue
                        qty = max_qty
                        cost = fill * qty
                        commission = cost * (cfg.commission_bps / 10000.0)
                    cash -= (cost + commission)
                    if sym in holdings:
                        prev = holdings[sym]
                        new_qty = prev["qty"] + qty
                        new_avg = (prev["qty"] * prev["avg_price"] + qty * fill) / new_qty
                        holdings[sym] = {"qty": new_qty, "avg_price": new_avg}
                    else:
                        holdings[sym] = {"qty": qty, "avg_price": fill}
                    trades.append({
                        "type": "fill", "side": "buy", "ticker": sym,
                        "date": dt.strftime("%Y-%m-%d"), "qty": qty,
                        "price": round(fill, 4),
                    })

        # Step 2: if today is a rebalance date, schedule the rebalance for tomorrow
        if dt in rebalance_set:
            # Trend filter on benchmark
            risk_on = (not mc.use_trend_filter or
                       benchmark_in_uptrend(bench_close, dt, mc.trend_filter_window))

            if risk_on or mc.risk_off_hold_count > 0:
                # Build price_data subset = current universe up to today
                pd_for_rank: dict[str, pd.DataFrame] = {}
                for sym in current_universe:
                    df = raw.get(sym)
                    if df is None:
                        continue
                    sub = df[df.index <= dt]
                    if len(sub) >= mc.lookback_long + mc.momentum_skip + 5:
                        pd_for_rank[sym] = sub
                picks = rank_universe(
                    price_data=pd_for_rank, as_of=dt,
                    lookbacks=(mc.lookback_short, mc.lookback_long),
                    weights=(mc.weight_short, mc.weight_long),
                    skip=mc.momentum_skip,
                    long_ma_window=mc.long_ma_window,
                    vol_window=mc.vol_window,
                    min_score=mc.min_momentum,
                    require_above_ma=mc.require_above_ma if risk_on else False,
                )

                if not risk_on:
                    # Sell weaker existing positions. Keep shares/weights of survivors;
                    # never buy a new name or reinvest cash while the filter is off.
                    scores = {p.ticker: p.score for p in picks}
                    ranked_held = sorted(holdings,
                        key=lambda sym: (-scores.get(sym, float('-inf')), sym))
                    keep = set(ranked_held[:min(mc.risk_off_hold_count, mc.n_hold)])
                    equity_now = cash
                    values = {}
                    for sym, h in holdings.items():
                        df = raw.get(sym)
                        price = (float(df.loc[dt, 'Close']) if df is not None and dt in df.index
                                 else h['avg_price'])
                        values[sym] = h['qty'] * price
                        equity_now += values[sym]
                    target_weights = {sym: values[sym] / equity_now for sym in keep}
                    continue_risk_off = True
                else:
                    continue_risk_off = False

                # Apply hysteresis: hold while in top-(n_hold + replacement_band)
                if not continue_risk_off and mc.replacement_band > 0 and holdings:
                    eligible = picks[: mc.n_hold + mc.replacement_band]
                    eligible_syms = {p.ticker for p in eligible}
                    # Build target list: kept holdings + top non-held to fill remaining slots
                    kept = [p for p in eligible if p.ticker in holdings]
                    held_set = {p.ticker for p in kept}
                    fillers = [p for p in picks
                               if p.ticker not in held_set
                               and p.ticker not in held_set
                               and p.ticker not in {h for h in holdings if h not in eligible_syms}]
                    # Remove from fillers any holding we're keeping (just in case)
                    fillers = [p for p in fillers if p.ticker not in held_set]
                    target_picks = kept + fillers[: max(0, mc.n_hold - len(kept))]
                    target_weights = _target_weights(
                        target_picks, mc.n_hold, mc.weighting, mc.target_total_exposure
                    )
                elif not continue_risk_off:
                    target_weights = _target_weights(picks, mc.n_hold,
                                                      mc.weighting, mc.target_total_exposure)

                # Optional weight-drift gate: skip rebalance if drift below threshold
                if (risk_on and mc.weight_drift_threshold > 0 and target_weights and holdings):
                    eq_now = cash
                    for sym, h in holdings.items():
                        df = raw.get(sym)
                        last_px = (float(df.loc[dt, "Close"])
                                    if df is not None and dt in df.index
                                    else h["avg_price"])
                        eq_now += h["qty"] * last_px
                    cur_w = {sym: (h["qty"] *
                                    (float(raw[sym].loc[dt, "Close"])
                                      if (sym in raw and dt in raw[sym].index)
                                      else h["avg_price"])) / max(eq_now, 1)
                              for sym, h in holdings.items()}
                    all_syms = set(cur_w) | set(target_weights)
                    drift = sum(abs(target_weights.get(s, 0) - cur_w.get(s, 0))
                                 for s in all_syms)
                    same_set = set(cur_w) == set(target_weights)
                    if same_set and drift < mc.weight_drift_threshold:
                        target_weights = None  # skip
            else:
                target_weights = {}   # explicit zero-retention variant

            if target_weights is not None:
                pending_rebalance = target_weights
                pending_hold_only = not risk_on
                trades.append({
                    "type": "rebalance", "date": dt.strftime("%Y-%m-%d"),
                    "risk_on": risk_on, "n_targets": len(target_weights),
                })

        # Step 3: mark-to-market with TODAY's close
        equity = cash
        for sym, h in holdings.items():
            df = raw.get(sym)
            if df is None or dt not in df.index:
                equity += h["qty"] * h["avg_price"]
                continue
            equity += h["qty"] * float(df.loc[dt, "Close"])
        equity_curve.append((dt, equity))

        # Snapshot holdings on rebalance days for reporting
        if dt in rebalance_set:
            holdings_history.append({
                "date": dt.strftime("%Y-%m-%d"),
                "n_holdings": len(holdings),
                "tickers": [s.replace(".NS", "") for s in holdings.keys()],
                "equity": round(equity, 2),
                "cash": round(cash, 2),
            })

    eq = pd.Series([v for _, v in equity_curve],
                    index=pd.DatetimeIndex([d for d, _ in equity_curve]))
    bench_curve = None
    if bench_close is not None:
        bench_curve = bench_close.reindex(eq.index).ffill().bfill()
        if not bench_curve.empty:
            bench_curve = bench_curve / bench_curve.iloc[0] * cfg.starting_capital

    latest_positions = []
    last_date = eq.index[-1]
    last_equity = float(eq.iloc[-1])
    for sym, h in holdings.items():
        df = raw.get(sym)
        price = float(df.loc[last_date, 'Close']) if df is not None and last_date in df.index else h['avg_price']
        latest_positions.append({'ticker': sym, 'weight': h['qty'] * price / last_equity,
                                 'price': price})
    return MomentumResult(
        latest_positions=latest_positions,
        equity_curve=eq, benchmark_curve=bench_curve,
        trades=trades, holdings_history=holdings_history,
        config={**cfg.to_dict(), **{f"momentum_{k}": v for k, v in mc.__dict__.items()}},
    )
