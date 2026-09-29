import os
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard.store import read_snapshot, write_snapshot


class StoreTest(unittest.TestCase):
    def test_public_remote_snapshot_is_cached(self):
        from dashboard.store import _remote_snapshot
        _remote_snapshot.cache_clear()
        with patch.dict(os.environ, {"RESEARCH_SNAPSHOT_URL": "https://example.test/snapshot.json"}), \
             patch("dashboard.store.urlopen", return_value=io.BytesIO(b'{"price_date":"2026-09-29"}')) as fetch:
            self.assertEqual(read_snapshot()["price_date"], "2026-09-29")
            self.assertEqual(read_snapshot()["price_date"], "2026-09-29")
            fetch.assert_called_once()
        _remote_snapshot.cache_clear()

    def test_public_file_snapshot_round_trip_without_database(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "RESEARCH_SNAPSHOT_FILE": str(Path(directory) / "state" / "current_snapshot.json"),
            "DATABASE_URL": "",
        }):
            self.assertIsNone(read_snapshot())
            write_snapshot({"price_date": "2026-09-28", "basket": {"positions": []}})
            self.assertEqual(read_snapshot()["price_date"], "2026-09-28")
            self.assertFalse(Path(directory, "state", "current_snapshot.json.tmp").exists())

    def test_atomic_snapshot_round_trip(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"RESEARCH_DB": str(Path(directory) / "research.sqlite"), "DATABASE_URL": ""}):
            self.assertIsNone(read_snapshot())
            write_snapshot({"price_date": "2026-09-25", "basket": {"positions": [{"ticker": "TEST.NS", "weight": 1.0}]}})
            self.assertEqual(read_snapshot()["basket"]["positions"][0]["weight"], 1.0)
            write_snapshot({"price_date": "2026-09-26", "basket": {"positions": []}})
            self.assertEqual(read_snapshot()["price_date"], "2026-09-26")


if __name__ == "__main__":
    unittest.main()
