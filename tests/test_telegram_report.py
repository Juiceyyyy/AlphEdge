import unittest

from jobs.telegram_report import report, subscribed_performance


class TelegramReportTests(unittest.TestCase):
    def test_subscription_performance_starts_after_signup_and_matches_cash_flows(self):
        forward = [
            {"date": "2026-01-30", "model_index": 100, "benchmark_index": 100},
            {"date": "2026-02-02", "model_index": 102, "benchmark_index": 101},
            {"date": "2026-02-03", "model_index": 99, "benchmark_index": 103},
            {"date": "2026-03-02", "model_index": 100, "benchmark_index": 104},
        ]
        subscriber = {"joined_date": "2026-02-01", "capital": 10000, "sip": 1000}
        actual = subscribed_performance(subscriber, forward)
        self.assertEqual(actual["since"], "2026-02-02")
        self.assertEqual(actual["paid"], 11000)
        self.assertAlmostEqual(actual["model"], 10000 * 100 / 102 + 1000)
        self.assertAlmostEqual(actual["nifty"], 10000 * 104 / 101 + 1000)
        self.assertLess(actual["drawdown_pct"], 0)

    def test_no_performance_without_a_close_after_subscription(self):
        self.assertIsNone(subscribed_performance(
            {"joined_date": "2026-03-01", "capital": 100, "sip": 0},
            [{"date": "2026-02-27", "model_index": 100, "benchmark_index": 100}]))

    def test_cash_report_shows_underlying_ranking_without_buy_instruction(self):
        subscriber = {"joined_date": "2026-10-01", "capital": 10000,
                      "sip": 500, "kpis": True}
        snapshot = {"price_date": "2026-10-02", "forward": [
            {"date": "2026-10-01", "model_index": 100, "benchmark_index": 100},
            {"date": "2026-10-02", "model_index": 100, "benchmark_index": 101}]}
        holdings = {"baskets": {
            "1/1/10": {"date": "2026-10-02", "risk_on": False, "positions": []},
            "0/1/15": {"positions": [{"ticker": "ABC.NS", "momentum": .42}]}}}
        text, target = report(subscriber, snapshot, holdings)
        self.assertIn("100% cash", text)
        self.assertIn("ABC", text)
        self.assertIn("not all are buys", text)
        self.assertIn("Nifty 50 price index", text)
        self.assertEqual(target["positions"], {})


if __name__ == "__main__":
    unittest.main()
