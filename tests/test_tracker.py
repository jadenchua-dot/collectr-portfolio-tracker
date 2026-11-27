"""Offline tests for the report maths. Run: python -m unittest discover -s tests -v"""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import tracker  # noqa: E402


def card(name, price, set_="Set", grade="Near Mint"):
    return {"name": name, "set": set_, "number": "", "grade": grade, "price": price,
            "qty": 1, "collectr_pct": 0, "collectr_diff": 0}


class Reports(unittest.TestCase):
    def setUp(self):
        self.old = {"a": card("Up", 100.0), "b": card("Down", 50.0), "c": card("Flat", 10.0)}
        self.new = {"a": card("Up", 110.0), "b": card("Down", 45.0), "c": card("Flat", 10.0)}
        self.history = {"2026-11-14": {"total": 160.0, "items": self.old}}

    def test_daily_lists_gainers_and_losers(self):
        msg = tracker.daily_report(165.0, self.new, self.history, "2026-11-15")
        self.assertIn("Since 2026-11-14: +$5.00 (+3.12%)", msg)
        self.assertIn("1. Up (Set · Near Mint)\n    $110.00  +10.00% (+$10.00)", msg)
        self.assertIn("1. Down (Set · Near Mint)\n    $45.00  -10.00% (-$5.00)", msg)
        self.assertNotIn("Flat (", msg)  # unchanged cards are neither gainers nor losers

    def test_weekly_waits_for_a_week_of_history(self):
        msg = tracker.weekly_report(165.0, self.new, self.history, "2026-11-15")
        self.assertIn("No snapshot from a week ago yet", msg)

    def test_weekly_compares_with_a_week_ago(self):
        history = {"2026-11-08": {"total": 160.0, "items": self.old}}
        msg = tracker.weekly_report(165.0, self.new, history, "2026-11-15")
        self.assertIn("This week: +$5.00 (+3.12%)", msg)
        self.assertIn("Best of the week: Up (Set · Near Mint) +10.00% (+$10.00)", msg)
        self.assertIn("Worst of the week: Down (Set · Near Mint) -10.00% (-$5.00)", msg)


class DryRun(unittest.TestCase):
    def test_dry_run_does_not_save_a_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_file, old_fetch = tracker.HISTORY_FILE, tracker.fetch_showcase
            tracker.HISTORY_FILE = pathlib.Path(tmp) / "history.json"
            tracker.fetch_showcase = lambda profile: (10.0, {"a": card("Only", 10.0)})
            try:
                tracker.cmd_run({"profile": "@x"}, dry_run=True)
                self.assertFalse(tracker.HISTORY_FILE.exists())
                tracker.cmd_run({"profile": "@x"}, dry_run=False)
                self.assertTrue(tracker.HISTORY_FILE.exists())
            finally:
                tracker.HISTORY_FILE, tracker.fetch_showcase = old_file, old_fetch


if __name__ == "__main__":
    unittest.main()
