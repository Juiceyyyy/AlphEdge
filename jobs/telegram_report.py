# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Private, opt-in Telegram research summaries using committed forward data.

The state file is Fernet-encrypted because this repository is public. Never log
the token, chat IDs, account preferences, or decrypted state.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken

STATE = Path("state/telegram_subscribers.enc")
SNAPSHOT = Path("state/current_snapshot.json")
HOLDINGS = Path("state/holdings_cache.json")
API = "https://api.telegram.org/bot"


class DeliveryError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Telegram delivery failed (HTTP {status})")


def money(value):
    return f"₹{value:,.0f}"


def percent(value):
    return f"{value:+.2f}%"


def api(method, payload):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    try:
        result = requests.post(API + token + "/" + method, json=payload, timeout=25)
    except requests.RequestException as exc:
        raise RuntimeError("Telegram connection failed") from None
    if result.status_code >= 400:
        raise DeliveryError(result.status_code)
    body = result.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method} returned an unsuccessful response")
    return body["result"]


def send(chat_id, message):
    if len(message) > 4096:
        raise ValueError("Telegram message too long; split the report into sections")
    api("sendMessage", {"chat_id": chat_id, "text": message,
                        "disable_web_page_preview": True})


def cipher():
    return Fernet(os.environ["TELEGRAM_STATE_KEY"].encode("ascii"))


def load_state():
    if not STATE.exists():
        return {"offset": 0, "subscribers": {}}
    try:
        value = json.loads(cipher().decrypt(STATE.read_bytes()))
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("Cannot decrypt subscriber state; check TELEGRAM_STATE_KEY") from exc
    if not isinstance(value.get("subscribers"), dict):
        raise ValueError("Invalid subscriber state")
    return value


def save_state(value):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".enc.tmp")
    temporary.write_bytes(cipher().encrypt(json.dumps(value, separators=(",", ":")).encode()))
    temporary.replace(STATE)


def market_data():
    snapshot = json.loads(SNAPSHOT.read_text())
    holdings = json.loads(HOLDINGS.read_text())
    day = snapshot["price_date"]
    if holdings["price_date"] != day:
        raise RuntimeError("Snapshot and rankings use different market closes")
    if (datetime.now(timezone.utc).date() - date.fromisoformat(day)).days > 5:
        raise RuntimeError("Market data is stale; no trade instructions sent")
    forward = snapshot["forward"]
    if not forward or forward[-1]["date"] != day:
        raise RuntimeError("Forward index is missing the latest market close")
    return snapshot, holdings


def subscribed_performance(subscriber, forward):
    """Close-to-close research index, adding SIP to both paths on the same day.

    No retroactive backtest is attributed to a subscriber. A subscription on a
    non-trading day begins with the next completed market close.
    """
    first = next((i for i, row in enumerate(forward)
                  if row["date"] >= subscriber["joined_date"]), None)
    if first is None or first >= len(forward) - 1:
        return None
    initial = subscriber["capital"]
    monthly = subscriber["sip"]
    model = nifty = paid = initial
    last_month = forward[first]["date"][:7]
    peak = forward[first]["model_index"]
    drawdown = 0.0
    for previous, current in zip(forward[first:-1], forward[first + 1:]):
        model *= current["model_index"] / previous["model_index"]
        nifty *= current["benchmark_index"] / previous["benchmark_index"]
        # Drawdown uses index units; new deposits cannot hide a loss.
        peak = max(peak, current["model_index"])
        drawdown = min(drawdown, current["model_index"] / peak - 1)
        month = current["date"][:7]
        if month != last_month:
            model += monthly
            nifty += monthly
            paid += monthly
            last_month = month
    return {"since": forward[first]["date"], "model": model, "nifty": nifty,
            "paid": paid, "model_pct": (model / paid - 1) * 100,
            "nifty_pct": (nifty / paid - 1) * 100,
            "drawdown_pct": drawdown * 100}


def ranking_lines(holdings):
    # Disabling the market trend gate reveals the underlying stock ranking even
    # while the actual default model is in cash; the stock filter remains on.
    ranked = holdings["baskets"]["0/1/15"]["positions"]
    return [f"{i:>2}. {p['ticker'].replace('.NS', ''):<13} "
            f"score {p['momentum']:+.2f}"
            for i, p in enumerate(ranked, 1)]


def report(subscriber, snapshot, holdings):
    day = snapshot["price_date"]
    target = holdings["baskets"]["1/1/10"]
    if target["date"] != day:
        raise RuntimeError("Target basket is not from the report's market close")
    previous = subscriber.get("last_target")
    current = {p["ticker"]: p["weight"] for p in target["positions"]}
    old = previous.get("positions", {}) if previous else {}
    entered = sorted(current.keys() - old.keys())
    exited = sorted(old.keys() - current.keys())
    changed = sorted(k for k in current.keys() & old.keys()
                     if abs(current[k] - old[k]) >= .005)
    fmt = lambda seq: ", ".join(s.replace(".NS", "") for s in seq) or "None"
    lines = ["ALPHEDGE  |  MONTHLY MODEL REVIEW", f"Market close: {day}",
             "Model: 10 stocks · monthly rebalance · Nifty 200-day filter",
             "", "MARKET & ALLOCATION",
             f"Nifty 200-day filter: {'ON — equity model' if target['risk_on'] else 'OFF — model in cash'}",
             f"Target: {len(current)} stocks · {100 if current else 0}% equity · {0 if current else 100}% cash",
             "", "TARGET HOLDINGS / WEIGHTS"]
    if current:
        lines += [f"{i:>2}. {p['ticker'].replace('.NS', ''):<13} {p['weight'] * 100:>5.1f}%"
                  for i, p in enumerate(target["positions"], 1)]
    else:
        lines.append("None. The current default model targets cash.")
    lines += ["", "CHANGES SINCE YOUR LAST REPORT"]
    if previous:
        lines += [f"New: {fmt(entered)}", f"Removed: {fmt(exited)}",
                  f"Weight moves ≥0.5 pp: {fmt(changed)}"]
        moves = [(symbol, old.get(symbol, 0), current.get(symbol, 0))
                 for symbol in sorted(current.keys() | old.keys())
                 if abs(current.get(symbol, 0) - old.get(symbol, 0)) >= .005]
        if moves:
            lines += ["Target weight changes:"]
            lines += [f"{symbol.replace('.NS', '')}: {before * 100:.1f}% → {after * 100:.1f}%"
                      for symbol, before, after in moves]
    else:
        lines.append("First report — no earlier target to compare.")
    lines += ["", "MODEL ACTION",
              "Default sell-to-cash model: hold cash until the trend filter clears."
              if not current else "Default model: review these target weights for the next interval.",
              "Review the new target versus your own holdings.",
              "The bot cannot know your shares or issue exact sell quantities.",
              "No orders are placed."]
    performance = subscribed_performance(subscriber, snapshot["forward"])
    if subscriber.get("kpis", True):
        lines += ["", "SINCE YOU SUBSCRIBED · HYPOTHETICAL"]
        if performance:
            lines += [f"From market close: {performance['since']}",
                      f"Contributed: {money(performance['paid'])}",
                      f"AlphEdge model: {money(performance['model'])} ({percent(performance['model_pct'])} vs contributions)",
                      f"Nifty 50 price index: {money(performance['nifty'])} ({percent(performance['nifty_pct'])} vs contributions)",
                      f"Difference: {performance['model_pct'] - performance['nifty_pct']:+.2f} percentage points",
                      f"Model drawdown since start: {percent(performance['drawdown_pct'])}"]
        else:
            lines.append("Starts after the next completed market close.")
        lines.append(f"Assumptions: {money(subscriber['capital'])} initial + {money(subscriber['sip'])}/month; no personal trades, tax or broker fees.")
    lines += ["", "UNDERLYING STOCK RANKING · TOP 15",
              "Ranked independently of the market filter; not all are buys."]
    lines += ranking_lines(holdings)
    lines += ["", "Research signals only. Returns track the published forward model, "
              "not your broker account; Nifty comparison excludes dividends."]
    message = "\n".join(lines)
    if len(message) > 4096:
        raise ValueError("Monthly report exceeds Telegram size")
    return message, {"date": day, "positions": current, "risk_on": target["risk_on"]}


HELP = ("ALPHEDGE BOT · SETTINGS\n"
        "/start — subscribe to the research updates\n"
        "/settings — view your assumptions\n"
        "/capital 10000 — starting amount in rupees\n"
        "/sip 5000 — monthly contribution in rupees\n"
        "/kpis on|off — show or hide performance section\n"
        "/now — send today's full report\n"
        "/stop — remove your subscription and stored settings\n\n"
        "Reports use the default 10-stock model. No broker connection or trading.")


def settings(subscriber):
    return ("YOUR REPORT SETTINGS\n"
            f"Started: {subscriber['joined_date']}\n"
            f"Initial amount: {money(subscriber['capital'])}\n"
            f"Monthly contribution: {money(subscriber['sip'])}\n"
            f"Performance KPIs: {'on' if subscriber['kpis'] else 'off'}\n"
            "Model: published 10-stock forward research index")


def handle(message, state):
    chat = message.get("chat", {})
    if chat.get("type") != "private" or not isinstance(message.get("text"), str):
        return
    chat_id = str(chat["id"])
    command, _, value = message["text"].strip().partition(" ")
    command = command.split("@", 1)[0].lower()
    subscribers = state["subscribers"]
    if command == "/start":
        if chat_id not in subscribers:
            if len(subscribers) >= 100:
                send(chat_id, "Subscription limit reached. Please try later.")
                return
            subscribers[chat_id] = {"joined_date": datetime.fromtimestamp(
                message["date"], timezone.utc).date().isoformat(),
                "capital": 10000, "sip": 0, "kpis": True}
        send(chat_id, "Subscribed. Your hypothetical comparison starts with the next completed market close.\n\n" + HELP)
        return
    if command == "/stop":
        subscribers.pop(chat_id, None)
        send(chat_id, "Subscription removed. Your settings have been deleted.")
        return
    if chat_id not in subscribers:
        send(chat_id, "Send /start to subscribe. No information is stored until then.")
        return
    subscriber = subscribers[chat_id]
    if command in ("/settings", "/help"):
        send(chat_id, settings(subscriber) if command == "/settings" else HELP)
    elif command == "/kpis" and value.strip().lower() in ("on", "off"):
        subscriber["kpis"] = value.strip().lower() == "on"
        send(chat_id, settings(subscriber))
    elif command in ("/capital", "/sip"):
        try:
            amount = int(value.strip().replace(",", ""))
            if not 0 <= amount <= 100_000_000 or (command == "/capital" and amount == 0):
                raise ValueError
        except ValueError:
            send(chat_id, "Enter a whole rupee amount, for example /capital 10000 or /sip 5000.")
            return
        subscriber["capital" if command == "/capital" else "sip"] = amount
        send(chat_id, settings(subscriber) + "\nFigures will be recalculated from your start date.")
    elif command == "/now":
        try:
            snapshot, holdings = market_data()
            message_text, _ = report(subscriber, snapshot, holdings)
            send(chat_id, message_text)
        except (OSError, ValueError, KeyError, RuntimeError):
            send(chat_id, "Market data is incomplete or stale. No report or trade action is available yet.")
    else:
        send(chat_id, HELP)


def run(mode):
    state = load_state()
    if mode in ("commands", "both"):
        # Persist the offset after each update so a failed run cannot repeat
        # successful messages to every subscriber on its next invocation.
        for update in api("getUpdates", {"offset": state["offset"], "timeout": 0,
                                         "allowed_updates": ["message"]}):
            state["offset"] = update["update_id"] + 1
            handle(update.get("message", {}), state)
            save_state(state)
    if mode in ("report", "both") and state["subscribers"]:
        try:
            snapshot, holdings = market_data()
        except (OSError, ValueError, KeyError, RuntimeError):
            print("Market data incomplete or stale; subscriber reports deferred")
            return
        day = snapshot["price_date"]
        for chat_id, subscriber in list(state["subscribers"].items()):
            previous = subscriber.get("last_target")
            new_month = not previous or previous["date"][:7] != day[:7]
            risk_changed = previous and previous["risk_on"] != holdings["baskets"]["1/1/10"]["risk_on"]
            if not new_month and not risk_changed:
                continue
            message_text, target = report(subscriber, snapshot, holdings)
            try:
                send(chat_id, message_text)
            except DeliveryError as exc:
                if exc.status in (400, 403):
                    # Bot blocked or chat deleted: remove the subscriber.
                    state["subscribers"].pop(chat_id, None)
                    save_state(state)
                    continue
                raise
            subscriber["last_target"] = target
            save_state(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("commands", "report", "both"))
    run(parser.parse_args().mode)
