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

    def test_completed_windows_are_archived_across_rebuilds(self):
        months=[{'date':f'{year}-{month:02d}-28','strategy_return':.01,
                 'benchmark_return':.005} for year in range(2020,2024) for month in range(1,13)]
        old={'data_through':'2024-01-28','variants':{'1/1/10':{'months':months}}}
        first=compile_cache(old)
        self.assertIn('2020',first['archived_windows']['1/1/10'])
        changed={'data_through':'2024-02-28','variants':{'1/1/10':{'months':[
            {**months[0],'strategy_return':-.5},*months[1:],
            {'date':'2024-02-28','strategy_return':.01,'benchmark_return':.005}]}}}
        newer=compile_cache(changed,first)
        self.assertEqual(newer['archived_windows']['1/1/10']['2020'],
                         first['archived_windows']['1/1/10']['2020'])
