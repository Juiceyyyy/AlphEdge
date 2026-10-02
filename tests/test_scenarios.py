# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
import unittest
from datetime import datetime, timezone

import pandas as pd

from alpha_strategy.backtest_momentum import MomentumResult
from jobs.build_scenarios import completed_sessions, monthly_path


class ScenarioCacheTest(unittest.TestCase):
    def test_incomplete_india_session_is_excluded(self):
        dates = pd.to_datetime(["2026-09-30", "2026-10-01"])
        data = {"^NSEI": pd.DataFrame({"Close": [100, 105]}, index=dates)}
        morning = completed_sessions(data, datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc))
        evening = completed_sessions(data, datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc))
        self.assertEqual(len(morning["^NSEI"]), 1)
        self.assertEqual(len(evening["^NSEI"]), 2)

    def test_partial_month_uses_latest_observed_date(self):
        dates = pd.to_datetime(["2026-08-28", "2026-09-28", "2026-09-30"])
        result = MomentumResult(
            equity_curve=pd.Series([100, 105, 110], index=dates),
            benchmark_curve=pd.Series([100, 102, 104], index=dates),
            trades=[], holdings_history=[], config={})
        path = monthly_path(result)
        self.assertEqual(path[-1]["date"], "2026-09-30")
        self.assertAlmostEqual(path[-1]["strategy_return"], 0.1)


if __name__ == "__main__":
    unittest.main()
