import tempfile
import unittest
from pathlib import Path

from smart_money_bot.watchlist import WatchlistStore


class WatchlistStoreTest(unittest.TestCase):
    def test_watchlist_creates_default_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.json"
            store = WatchlistStore(path, default_symbols=["ENAUSDT", "SUIUSDT"])

            self.assertEqual(store.load(), ["ENAUSDT", "SUIUSDT"])
            self.assertTrue(path.exists())

    def test_watchlist_normalizes_symbols_and_avoids_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.json"
            store = WatchlistStore(path, default_symbols=[])

            self.assertTrue(store.add(" enausdt "))
            self.assertFalse(store.add("ENAUSDT"))
            self.assertEqual(store.load(), ["ENAUSDT"])

    def test_watchlist_remove_persists_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.json"
            store = WatchlistStore(path, default_symbols=["ENAUSDT", "SUIUSDT"])

            self.assertTrue(store.remove("enausdt"))
            self.assertFalse(store.remove("missing"))
            self.assertEqual(store.load(), ["SUIUSDT"])


if __name__ == "__main__":
    unittest.main()
