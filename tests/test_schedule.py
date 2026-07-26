from __future__ import annotations

import unittest
from datetime import datetime

from timelapse_manager.errors import ConfigError
from timelapse_manager.schedule import select_next_slot


class ScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.morning = {"start_at": "03:00", "end_at": "09:00"}
        self.dusk = {"start_at": "16:00", "end_at": "20:00"}

    def test_selects_morning_before_and_during_window(self) -> None:
        before = select_next_slot(self.morning, self.dusk, datetime(2026, 7, 21, 1, 0))
        during = select_next_slot(self.morning, self.dusk, datetime(2026, 7, 21, 8, 59))
        self.assertEqual(
            (before.label, before.work_date.isoformat()), ("清晨", "2026-07-21")
        )
        self.assertEqual(during.label, "清晨")

    def test_selects_dusk_after_morning(self) -> None:
        slot = select_next_slot(self.morning, self.dusk, datetime(2026, 7, 21, 12, 0))
        self.assertEqual((slot.label, slot.directory_name), ("黄昏", "1600-2000"))

    def test_selects_next_day_after_dusk(self) -> None:
        slot = select_next_slot(self.morning, self.dusk, datetime(2026, 7, 21, 20, 0))
        self.assertEqual(
            (slot.label, slot.work_date.isoformat()), ("清晨", "2026-07-22")
        )

    def test_rejects_overlapping_ranges(self) -> None:
        with self.assertRaises(ConfigError):
            select_next_slot(self.morning, {"start_at": "08:00", "end_at": "20:00"})


if __name__ == "__main__":
    unittest.main()
