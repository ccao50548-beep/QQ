"""End-to-end tests for JingcaiDesk V2.2 on Windows/Linux.

The source database sessions must close connections BEFORE TemporaryDirectory
cleans up, or Windows raises WinError 32 on test.sqlite3.
"""
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import core
import official
import report

DAY = "2026-11-04"


class EndToEnd(unittest.TestCase):
    def test_verified_segregated_and_report(self):
        with tempfile.TemporaryDirectory(prefix="jingcai_fixture_") as folder:
            db_file = pathlib.Path(folder) / "test.sqlite3"
            with patch.object(core, "DB", db_file), patch.object(official, "DB", db_file):
                count = official.store([{
                    "jc_no": "周三001", "date": DAY,
                    "kickoff": "2026-11-04 20:00", "league": "模拟",
                    "home": "Team H", "away": "Team A",
                }], "测试CSV")
                self.assertEqual(count, 1)
                match = official.load(DAY)[0]
                self.assertEqual(match["review_state"], "待核对")
                self.assertIsNone(match["home_xg"])
                official.record_confirmation(DAY, "周三001", True)
                self.assertEqual(official.load(DAY)[0]["review_state"], "用户已核对官方页面")
                output = pathlib.Path(folder) / "report.html"
                report.export(output, DAY)
                self.assertIn("暂无充分赛前数据", output.read_text(encoding="utf-8"))
                # Verify every SQLite handle has been closed, not just committed.
                with db_file.open("rb+") as handle:
                    self.assertTrue(handle.read(16).startswith(b"SQLite format 3"))
            # Must succeed on Windows too; do not ignore cleanup errors.
        self.assertFalse(pathlib.Path(folder).exists())

    def test_historical_matching_no_future(self):
        with tempfile.TemporaryDirectory(prefix="jingcai_history_") as folder:
            db_file = pathlib.Path(folder) / "test.sqlite3"
            with patch.object(core, "DB", db_file), patch.object(official, "DB", db_file):
                official.store([{
                    "jc_no": "周三001", "date": DAY,
                    "kickoff": "2026-11-04 20:00", "league": "模拟",
                    "home": "Home United", "away": "Away City",
                }], "mock")
                target = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
                entries = []
                for k in range(6):
                    entries.append({
                        "id": 100 + k,
                        "utcDate": (target - timedelta(days=(k + 1) * 7)).isoformat(),
                        "status": "FINISHED",
                        "homeTeam": {"id": 1, "name": "Home United"},
                        "awayTeam": {"id": 2, "name": "Away City"},
                        "score": {"fullTime": {"home": 2, "away": 1}},
                    })
                entries.append({
                    "id": 999, "utcDate": target.isoformat(), "status": "TIMED",
                    "homeTeam": {"id": 1, "name": "Home United"},
                    "awayTeam": {"id": 2, "name": "Away City"},
                    "score": {"fullTime": {"home": None, "away": None}},
                })
                with patch("sources.request_json", return_value={"matches": entries}):
                    count, errors = official.enrich_from_football_data(DAY, "fake", ["PL"])
                self.assertEqual(count, 1, str(errors))
                result = official.load(DAY)[0]
                self.assertIsNotNone(result["home_xg"])
                self.assertGreaterEqual(result["history_home"], 5)
                future = dict(entries[0])
                future["id"] = 777
                future["utcDate"] = (target + timedelta(days=5)).isoformat()
                future["score"] = {"fullTime": {"home": 50, "away": 0}}
                with patch("sources.request_json", return_value={"matches": entries + [future]}):
                    official.enrich_from_football_data(DAY, "fake", ["PL"])
                self.assertAlmostEqual(result["home_xg"], official.load(DAY)[0]["home_xg"])
        self.assertFalse(pathlib.Path(folder).exists())


if __name__ == "__main__":
    unittest.main()
