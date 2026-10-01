import unittest
from jobs.build_research_cache import compile_cache

class CacheTest(unittest.TestCase):
    def test_completed_year_is_frozen_and_active_year_rolls(self):
        old={'data_through':'2026-12-31','variants':{'1/1/10':{'months':[
            {'date':'2026-01-31','strategy_return':.1,'benchmark_return':.05},
            {'date':'2026-12-31','strategy_return':.2,'benchmark_return':.05}]}}}
        archived=compile_cache(old)
        self.assertEqual(archived['variants']['1/1/10']['annual'][0]['year'],2026)
        rollover={'data_through':'2027-01-31','variants':{'1/1/10':{'months':old['variants']['1/1/10']['months']+[
            {'date':'2027-01-31','strategy_return':.03,'benchmark_return':.01}]}}}
        result=compile_cache(rollover,archived)
        self.assertAlmostEqual(result['archived']['1/1/10']['2026']['return_pct'],32.0)
        self.assertEqual(result['variants']['1/1/10']['annual'][-1]['year'],2027)
        self.assertTrue(result['variants']['1/1/10']['annual'][-1]['active'])
