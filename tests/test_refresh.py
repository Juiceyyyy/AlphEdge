# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
import unittest
from unittest.mock import patch
import pandas as pd
from jobs import refresh


class RefreshTest(unittest.TestCase):
    def test_initial_snapshot_has_no_claimed_return(self):
        basket={"date":"2026-09-25","benchmark_close":100.0,"risk_on":True,
                "positions":[{"ticker":"EXAMPLE.NS","price":50.0,"weight":1.0}]}
        with patch.object(refresh,"read_snapshot",return_value=None), patch.object(refresh,"_current_candidates",return_value=basket), patch.object(refresh,"write_snapshot") as write:
            refresh.refresh()
        snapshot=write.call_args.args[0]
        self.assertEqual(snapshot["forward"][0]["model_index"],100)
        self.assertEqual(snapshot["price_date"],"2026-09-25")

    def test_next_close_uses_previous_basket_and_publishes_once(self):
        basket={"date":"2026-09-25","benchmark_close":100.0,"risk_on":True,
                "positions":[{"ticker":"EXAMPLE.NS","price":50.0,"weight":1.0}]}
        previous={"price_date":"2026-09-25","basket":basket,
                  "forward":[{"date":"2026-09-25","model_index":100.0,"benchmark_index":100.0}]}
        data={"^NSEI":pd.DataFrame({"Close":[101.0]},index=pd.to_datetime(["2026-09-28"])),
              "EXAMPLE.NS":pd.DataFrame({"Close":[55.0]},index=pd.to_datetime(["2026-09-28"]))}
        with patch.object(refresh,"read_snapshot",return_value=previous), patch.object(refresh,"download_history",return_value=data), patch.object(refresh,"write_snapshot") as write:
            refresh.refresh()
        snapshot=write.call_args.args[0]
        self.assertAlmostEqual(snapshot["forward"][-1]["model_index"],110)
        self.assertAlmostEqual(snapshot["forward"][-1]["benchmark_index"],101)
        self.assertEqual(snapshot["basket"]["positions"][0]["price"],55)

    def test_missing_close_never_publishes(self):
        previous={"price_date":"2026-09-25","basket":{"date":"2026-09-25","benchmark_close":100,
                  "positions":[{"ticker":"MISSING.NS","price":50,"weight":1}]},
                  "forward":[{"date":"2026-09-25","model_index":100,"benchmark_index":100}]}
        data={"^NSEI":pd.DataFrame({"Close":[101]},index=pd.to_datetime(["2026-09-28"]))}
        with patch.object(refresh,"read_snapshot",return_value=previous), patch.object(refresh,"download_history",return_value=data), patch.object(refresh,"write_snapshot") as write:
            with self.assertRaises(RuntimeError): refresh.refresh()
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
