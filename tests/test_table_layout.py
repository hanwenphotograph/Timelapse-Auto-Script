from __future__ import annotations

import unittest

from timelapse_manager.ui.table import responsive_column_widths


class TableLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.columns = (
            "name",
            "preset",
            "status",
            "phase",
            "progress",
            "pid",
            "started",
        )
        self.widths = {
            "name": 260,
            "preset": 70,
            "status": 70,
            "phase": 180,
            "progress": 280,
            "pid": 70,
            "started": 210,
        }

    def test_columns_fill_the_available_width(self) -> None:
        result = responsive_column_widths(self.columns, self.widths, 1400)

        self.assertEqual(sum(result.values()), 1400)

    def test_short_columns_stay_narrower_than_long_columns(self) -> None:
        result = responsive_column_widths(self.columns, self.widths, 1400)

        self.assertLess(result["preset"], result["name"])
        self.assertLess(result["pid"], result["progress"])
        self.assertLess(result["status"], result["started"])

    def test_small_viewport_still_has_no_width_overflow(self) -> None:
        result = responsive_column_widths(self.columns, self.widths, 300)

        self.assertEqual(sum(result.values()), 300)
        self.assertTrue(all(width >= 0 for width in result.values()))


if __name__ == "__main__":
    unittest.main()
