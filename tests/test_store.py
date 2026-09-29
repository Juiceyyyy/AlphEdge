import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard.store import read_snapshot, write_snapshot


class StoreTest(unittest.TestCase):
    def test_atomic_snapshot_round_trip(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"RESEARCH_DB": str(Path(directory) / "research.sqlite"), "DATABASE_URL": ""}):
            self.assertIsNone(read_snapshot())
            write_snapshot({"price_date": "2026-09-25", "basket": {"positions": [{"ticker": "TEST.NS", "weight": 1.0}]}})
            self.assertEqual(read_snapshot()["basket"]["positions"][0]["weight"], 1.0)
            write_snapshot({"price_date": "2026-09-26", "basket": {"positions": []}})
            self.assertEqual(read_snapshot()["price_date"], "2026-09-26")


if __name__ == "__main__":
    unittest.main()
