# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Explicit-plan CNC rebalance for an individual's locally managed Kite account.

The public research server never imports or calls this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from alpha_strategy.config import StrategyConfig, load_env
from alpha_strategy.data import download_history
from alpha_strategy.universe import to_yahoo_symbol
from jobs.build_scenarios import completed_sessions
from dashboard.explorer import _current_candidates
from .kite import KiteClient

IST = ZoneInfo("Asia/Kolkata")
STATE = Path(os.getenv("BROKER_STATE_DIR", "var/broker"))


def _positive_limit(name):
    value = float(os.getenv(name, "0"))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Set a positive {name} in the local environment")
    return value


def _json(path, fallback):
    return json.loads(path.read_text()) if path.exists() else fallback


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(temporary, path)


def _quarter(today):
    return f"{today.year}-Q{(today.month - 1) // 3 + 1}"


def _check_cadence(today):
    months = {int(m.strip()) for m in os.getenv("REBALANCE_MONTHS", "3,6,9,12").split(",")}
    if today.month not in months or any(m < 1 or m > 12 for m in months):
        raise RuntimeError("Quarterly rebalance is outside the configured earnings review months")
    for journal in STATE.glob("execution_*.json"):
        record = _json(journal, {})
        if record.get("status") == "complete" and record.get("quarter") == _quarter(today):
            raise RuntimeError("A rebalance already completed this quarter")


def _check_earnings(targets, today):
    if os.getenv("EARNINGS_GATE", "required").lower() != "required":
        return {}
    dates = _json(STATE / "earnings_clearance.json", {})
    selected = {}
    for symbol in targets:
        try:
            released = date.fromisoformat(dates[symbol])
        except (KeyError, ValueError, TypeError):
            raise RuntimeError(f"Record and review {symbol}'s latest earnings release date before planning")
        if not 0 <= (today - released).days <= 120:
            raise RuntimeError(f"{symbol}'s earnings clearance is outside the last 120 days")
        selected[symbol] = released.isoformat()
    return selected


def _reference_prices(client, symbols, today):
    if os.getenv("BROKER_QUOTE_SOURCE", "public").lower() == "broker":
        quotes = client.ltp(symbols)
        return {s: float(quotes[f"NSE:{s}"]["last_price"]) for s in symbols}
    raw = completed_sessions(download_history([to_yahoo_symbol(s) for s in symbols] + ["^NSEI"],
                                              years=1, cache_dir=Path("cache/ohlcv"), refresh_days=0))
    benchmark = raw.get("^NSEI")
    if benchmark is None or benchmark.empty:
        raise RuntimeError("Public reference prices unavailable")
    session = benchmark.index.max()
    if (today - session.date()).days > 4:
        raise RuntimeError("Public reference price date is stale")
    prices = {}
    for symbol in symbols:
        frame = raw.get(to_yahoo_symbol(symbol))
        if frame is None or frame.empty or session not in frame.index:
            raise RuntimeError(f"No matching public close for {symbol}")
        prices[symbol] = float(frame.loc[session, "Close"])
    return prices


def _limit_price(side, reference):
    # A resting limit caps a buy and sets a floor for a sale. No market order
    # can slip beyond the user's chosen bound when using delayed free prices.
    bound = reference * (1.01 if side == "BUY" else .99)
    return round((math.floor(bound / .05) if side == "BUY" else math.ceil(bound / .05)) * .05, 2)


def build_plan(client):
    cfg = StrategyConfig.from_yaml("config.yaml")
    today = datetime.now(IST).date()
    cap = _positive_limit("MAX_CAPITAL_INR")
    per_order = _positive_limit("MAX_ORDER_NOTIONAL_INR")
    managed = set(_json(STATE / "managed_symbols.json", []))
    existing = {h["tradingsymbol"]: int(h.get("quantity", 0)) + int(h.get("t1_quantity", 0))
                for h in client.holdings() if h.get("exchange") == "NSE" and h.get("product") == "CNC"}
    held_managed = sorted(s for s in managed if existing.get(s, 0) > 0)
    held_prices = _reference_prices(client, held_managed, today) if held_managed else {}
    prior = {"positions": [{"ticker": to_yahoo_symbol(sym), "weight": existing[sym] * held_prices[sym] / cap,
                             "price": held_prices[sym]} for sym in held_managed]}
    if sum(p['weight'] for p in prior['positions']) > 1.02:
        raise RuntimeError('Managed holdings exceed MAX_CAPITAL_INR; increase the explicit limit before planning')
    basket = _current_candidates(cfg.use_trend_filter, cfg.require_above_ma, cfg.n_hold,
                                 previous=prior, risk_off_hold_count=cfg.risk_off_hold_count)
    if (today - date.fromisoformat(basket["date"])).days > 4:
        raise RuntimeError("Model price date is stale; no plan generated")
    if basket["risk_on"]:
        _check_cadence(today)  # regular expansion stays quarterly and earnings-reviewed
    target_symbols = {p["ticker"].removesuffix(".NS") for p in basket["positions"]}
    symbols = sorted(target_symbols | managed)
    if not symbols:
        raise RuntimeError("No target or managed positions to review")
    clearance = _check_earnings(target_symbols, today) if basket["risk_on"] else {}
    prices = _reference_prices(client, symbols, today)
    if any(not math.isfinite(p) or p <= 0 for p in prices.values()):
        raise RuntimeError("Invalid broker quotes")
    targets = ({p["ticker"].removesuffix(".NS"): math.floor(cap * p["weight"] / prices[p["ticker"].removesuffix(".NS")])
                for p in basket["positions"]} if basket["risk_on"] else
               {sym: existing.get(sym, 0) for sym in target_symbols})  # no buys/resizing in risk-off
    orders = []
    for symbol in symbols:
        owned = existing.get(symbol, 0) if symbol in managed else 0
        desired = targets.get(symbol, 0)
        delta = desired - owned
        if delta == 0:
            continue
        if symbol not in managed and symbol in existing and existing[symbol] > 0:
            raise RuntimeError(f"{symbol} is held outside this runner; add it to managed_symbols.json only after review")
        notional = abs(delta) * prices[symbol]
        if notional > per_order:
            raise RuntimeError(f"{symbol} exceeds MAX_ORDER_NOTIONAL_INR")
        orders.append({"side": "BUY" if delta > 0 else "SELL", "symbol": symbol,
                       "quantity": abs(delta), "quote": prices[symbol], "estimated_notional": round(notional, 2)})
    if sum(o["estimated_notional"] for o in orders) > cap * 1.25:
        raise RuntimeError("Turnover exceeds 125% of configured capital")
    plan = {"created_at": datetime.now(timezone.utc).isoformat(), "price_date": basket["date"],
            "capital_limit": cap, "risk_on": basket["risk_on"], "orders": orders,
            "quarter": _quarter(today), "earnings_clearance": clearance,
            "reference_source": os.getenv("BROKER_QUOTE_SOURCE", "public"),
            "managed_symbols": sorted(managed), "target_symbols": sorted(target_symbols)}
    plan["id"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:16]
    return plan


def execute(client, plan, confirmation):
    if os.getenv("TRADING_ENABLED", "false").lower() != "true":
        raise RuntimeError("TRADING_ENABLED must be true in the local runner")
    if os.getenv("BROKER_IP_CONFIRMED", "false").lower() != "true":
        raise RuntimeError("Confirm this machine uses the broker-registered static IP")
    unsigned = {key: value for key, value in plan.items() if key != "id"}
    digest = hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest()[:16]
    if confirmation != plan["id"] or digest != plan["id"]:
        raise RuntimeError("Plan confirmation ID mismatch or plan file changed")
    now = datetime.now(IST)
    if now.date() != datetime.fromisoformat(plan["created_at"].replace("Z", "+00:00")).astimezone(IST).date():
        raise RuntimeError("Plan must be generated today")
    if now.weekday() >= 5 or not time(9, 20) <= now.time() <= time(15, 10):
        raise RuntimeError("Orders only allowed during the configured NSE session window")
    if (datetime.now(timezone.utc) - datetime.fromisoformat(plan["created_at"])).total_seconds() > 900:
        raise RuntimeError("Plan expired after 15 minutes")
    journal_path = STATE / f"execution_{plan['id']}.json"
    if journal_path.exists():
        raise RuntimeError("Plan already started; reconcile its journal and broker order book before proceeding")
    current = {h["tradingsymbol"]: int(h.get("quantity", 0)) + int(h.get("t1_quantity", 0))
               for h in client.holdings() if h.get("exchange") == "NSE" and h.get("product") == "CNC"}
    for order in plan["orders"]:
        symbol = order["symbol"]
        if order["side"] == "SELL" and current.get(symbol, 0) < order["quantity"]:
            raise RuntimeError(f"Insufficient {symbol} holdings")
    _check_cadence(now.date())
    journal = {"plan_id": plan["id"], "quarter": plan["quarter"], "started_at": now.isoformat(), "orders": [], "status": "started"}
    _write(journal_path, journal)
    for order in sorted(plan["orders"], key=lambda o: o["side"] != "SELL"):
        quote = _reference_prices(client, [order["symbol"]], now.date())[order["symbol"]]
        if abs(quote / order["quote"] - 1) > 0.02:
            raise RuntimeError(f"{order['symbol']} quote moved more than 2%; stop and replan")
        if order["side"] == "BUY":
            available = float(client.margins()["available"]["live_balance"])
            if available < order["quantity"] * quote * 1.02:
                raise RuntimeError(f"Insufficient available funds for {order['symbol']}")
        # Journal intent before sending: an ambiguous network failure must never auto-retry.
        entry = {**order, "status": "submitting"}
        journal["orders"].append(entry); _write(journal_path, journal)
        order_id = client.place(order["side"], order["symbol"], order["quantity"],
                                tag="MAT" + plan["id"][:12], limit_price=_limit_price(order["side"], quote))
        entry.update(order_id=order_id, status="submitted"); _write(journal_path, journal)
        # Placement is not a fill. Stop for manual reconciliation on any open or rejected order.
        history = client.order_history(order_id)
        status = history[-1]["status"] if history else "UNKNOWN"
        entry["status"] = status; _write(journal_path, journal)
        if status != "COMPLETE":
            raise RuntimeError(f"{order_id} status {status}; reconcile manually before any new run")
    managed = set(plan["managed_symbols"]) | set(plan["target_symbols"])
    _write(STATE / "managed_symbols.json", sorted(managed))
    journal["status"] = "complete"; _write(journal_path, journal)
    return journal


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Local, opt-in Kite CNC strategy runner")
    parser.add_argument("command", choices=["plan", "execute"])
    parser.add_argument("--plan-file", default="var/broker/latest_plan.json")
    parser.add_argument("--confirm", help="Exact plan ID printed during plan review")
    args = parser.parse_args()
    client = KiteClient()
    if args.command == "plan":
        plan = build_plan(client)
        _write(Path(args.plan_file), plan)
        print(json.dumps(plan, indent=2))
        print(f"Review every proposed order. To execute today: python -m broker.runner execute --confirm {plan['id']}")
    else:
        plan = _json(Path(args.plan_file), None)
        if not plan: raise RuntimeError("No saved plan")
        print(json.dumps(execute(client, plan, args.confirm), indent=2))


if __name__ == "__main__":
    main()
