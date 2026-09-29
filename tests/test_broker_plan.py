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
            with patch.object(runner, "STATE", path), patch.object(runner, "_current_candidates", return_value=basket), patch.dict(os.environ, {"MAX_CAPITAL_INR": "1000", "MAX_ORDER_NOTIONAL_INR": "2000"}):
                plan = runner.build_plan(FakeClient())
            self.assertEqual([(o["side"], o["symbol"], o["quantity"]) for o in plan["orders"]],
                             [("BUY", "NEW", 10), ("SELL", "OLD", 2)])
            self.assertNotIn("PERSONAL", plan["managed_symbols"])

    def test_execution_disabled_by_default(self):
        with patch.dict(os.environ, {"TRADING_ENABLED": "false"}):
            with self.assertRaisesRegex(RuntimeError, "TRADING_ENABLED"):
                runner.execute(FakeClient(), {"id": "example"}, "example")


if __name__ == "__main__":
    unittest.main()
