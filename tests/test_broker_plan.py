# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from broker import runner


class FakeClient:
    def holdings(self):
        return [{"exchange": "NSE", "product": "CNC", "tradingsymbol": "OLD", "quantity": 2, "t1_quantity": 0},
                {"exchange": "NSE", "product": "CNC", "tradingsymbol": "PERSONAL", "quantity": 10, "t1_quantity": 0}]
    def ltp(self, symbols):
        return {f"NSE:{symbol}": {"last_price": 100.0} for symbol in symbols}
    def place(self, *args, **kwargs):
        raise AssertionError("Planning must never place orders")


class BrokerPlanTest(unittest.TestCase):
    def test_plan_only_managed_sales_and_target_buy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "managed_symbols.json").write_text('["OLD"]')
            today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
            basket = {"date": today, "risk_on": True, "positions": [{"ticker": "NEW.NS", "weight": 1.0}]}
            with patch.object(runner, "STATE", path), patch.object(runner, "_current_candidates", return_value=basket), patch.dict(os.environ, {"MAX_CAPITAL_INR": "1000", "MAX_ORDER_NOTIONAL_INR": "2000", "REBALANCE_MONTHS": str(datetime.now(ZoneInfo("Asia/Kolkata")).month), "EARNINGS_GATE": "off", "BROKER_QUOTE_SOURCE": "broker"}):
                plan = runner.build_plan(FakeClient())
            self.assertEqual([(o["side"], o["symbol"], o["quantity"]) for o in plan["orders"]],
                             [("BUY", "NEW", 10), ("SELL", "OLD", 2)])
            self.assertNotIn("PERSONAL", plan["managed_symbols"])

    def test_quarterly_and_earnings_gates_block_unreviewed_orders(self):
        with tempfile.TemporaryDirectory() as directory:
            today=datetime.now(ZoneInfo("Asia/Kolkata")).date()
            basket={"date":today.isoformat(),"risk_on":True,"positions":[{"ticker":"NEW.NS","weight":1.0}]}
            with patch.object(runner,"STATE",Path(directory)), patch.object(runner,"_current_candidates",return_value=basket), patch.dict(os.environ,{"MAX_CAPITAL_INR":"1000","MAX_ORDER_NOTIONAL_INR":"2000","REBALANCE_MONTHS":str(today.month),"EARNINGS_GATE":"required","BROKER_QUOTE_SOURCE":"broker"}):
                with self.assertRaisesRegex(RuntimeError,"earnings release date"):
                    runner.build_plan(FakeClient())
                (Path(directory)/"earnings_clearance.json").write_text('{"NEW":"'+today.isoformat()+'"}')
                plan=runner.build_plan(FakeClient())
                self.assertEqual(plan['earnings_clearance']['NEW'],today.isoformat())
                self.assertEqual(plan['quarter'],runner._quarter(today))

    def test_limit_prices_bound_orders(self):
        self.assertLessEqual(runner._limit_price('BUY',100),101)
        self.assertGreaterEqual(runner._limit_price('SELL',100),99)

    def test_execution_disabled_by_default(self):
        with patch.dict(os.environ, {"TRADING_ENABLED": "false"}):
            with self.assertRaisesRegex(RuntimeError, "TRADING_ENABLED"):
                runner.execute(FakeClient(), {"id": "example"}, "example")


if __name__ == "__main__":
    unittest.main()
