# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Small Kite Connect v3 client for a user's own local runner."""
import os
from pathlib import Path
import requests

BASE = "https://api.kite.trade"


class KiteError(RuntimeError):
    pass


class KiteClient:
    def __init__(self, api_key=None, access_token=None, session=None):
        self.api_key = api_key or os.getenv("KITE_API_KEY")
        token_file = Path(os.getenv("BROKER_STATE_DIR", "var/broker")) / "access_token"
        self.access_token = access_token or os.getenv("KITE_ACCESS_TOKEN") or (token_file.read_text().strip() if token_file.exists() else None)
        if not self.api_key or not self.access_token:
            raise KiteError("Set KITE_API_KEY and today's KITE_ACCESS_TOKEN locally")
        self.session = session or requests.Session()

    def request(self, method, path, *, params=None, data=None):
        try:
            response = self.session.request(method, BASE + path, params=params, data=data,
                headers={"X-Kite-Version": "3", "Authorization": f"token {self.api_key}:{self.access_token}"},
                timeout=20)
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise KiteError(f"Broker request failed for {path}: {type(exc).__name__}") from exc
        if result.get("status") != "success":
            raise KiteError(f"Broker rejected {path}: {result.get('error_type', 'unknown error')}")
        return result["data"]

    def holdings(self):
        return self.request("GET", "/portfolio/holdings")

    def margins(self):
        return self.request("GET", "/user/margins/equity")

    def ltp(self, tickers):
        return self.request("GET", "/quote/ltp", params=[("i", f"NSE:{symbol}") for symbol in tickers])

    def place(self, side, symbol, quantity, *, tag, limit_price):
        if side not in ("BUY", "SELL") or quantity <= 0 or limit_price <= 0:
            raise ValueError("Invalid order")
        result = self.request("POST", "/orders/regular", data={
            "exchange": "NSE", "tradingsymbol": symbol,
            "transaction_type": side, "order_type": "LIMIT", "price": limit_price,
            "quantity": quantity, "product": "CNC", "validity": "DAY",
            "tag": tag,
        })
        return result["order_id"]

    def order_history(self, order_id):
        return self.request("GET", f"/orders/{order_id}")
