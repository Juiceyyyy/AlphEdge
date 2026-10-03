# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Keep existing winners without replacing or reweighting them below the trend filter."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from dashboard import explorer


class RiskOffBasketTest(unittest.TestCase):
    def test_retains_five_existing_holdings_and_leaves_sale_proceeds_in_cash(self):
        date = pd.Timestamp('2026-10-01')
        prior = {'positions': [{'ticker': f'S{i}.NS', 'price': 100, 'weight': .1}
                               for i in range(10)]}
        prices = {p['ticker']: pd.DataFrame({'Close': [100], 'Volume': [1000]},
                  index=[date]) for p in prior['positions']}
        prices['NEW.NS'] = pd.DataFrame({'Close': [100], 'Volume': [1000]}, index=[date])
        prices['^NSEI'] = pd.DataFrame({'Close': [100]}, index=[date])
        ranking = [SimpleNamespace(ticker='NEW.NS', score=99, vol=.2, price=100)] + [
            SimpleNamespace(ticker=f'S{i}.NS', score=10-i, vol=.2, price=100)
            for i in range(10)]
        with patch.object(explorer, 'rank_by_adtv', return_value=list(prices)), \
             patch.object(explorer, 'rank_universe', return_value=ranking), \
             patch.object(explorer, 'benchmark_in_uptrend', return_value=False):
            result = explorer._current_candidates(True, True, 10, prepared=prices,
                universe=list(prices), previous=prior, risk_off_hold_count=5)
            cash = explorer._current_candidates(True, True, 10, prepared=prices,
                universe=list(prices), previous=prior, risk_off_hold_count=0)
        self.assertEqual([p['ticker'] for p in result['positions']],
                         [f'S{i}.NS' for i in range(5)])
        self.assertAlmostEqual(sum(p['weight'] for p in result['positions']), .5)
        self.assertEqual(cash['positions'], [])


if __name__ == '__main__':
    unittest.main()
