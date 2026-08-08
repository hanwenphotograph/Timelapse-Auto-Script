from __future__ import annotations

import unittest

from timelapse_manager.child_progress import update_child_progress


class ChildProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            {"role": "bracketlapse-standby", "status": "completed"},
            {
                "role": "bracketlapse-standby",
                "status": "running",
                "progress": {"completed": 1, "total": 2},
            },
        ]

    def test_updates_each_count_independently_on_latest_running_child(self) -> None:
        records, changed = update_child_progress(
            self.records,
            "bracketlapse-standby",
            total=4,
            phase="HDR处理",
        )

        self.assertTrue(changed)
        self.assertNotIn("progress", records[0])
        self.assertEqual(records[1]["progress"], {"completed": 1, "total": 4})
        self.assertEqual(records[1]["phase"], "HDR处理")

        records, changed = update_child_progress(
            records,
            "bracketlapse-standby",
            completed=2,
        )

        self.assertTrue(changed)
        self.assertEqual(records[1]["progress"], {"completed": 2, "total": 4})

    def test_unchanged_or_lower_counts_do_not_trigger_write(self) -> None:
        records, changed = update_child_progress(
            self.records,
            "bracketlapse-standby",
            completed=1,
            total=2,
        )

        self.assertFalse(changed)
        self.assertEqual(records, self.records)

    def test_completed_count_also_raises_total(self) -> None:
        records, _changed = update_child_progress(
            self.records,
            "bracketlapse-standby",
            completed=3,
        )

        self.assertEqual(records[1]["progress"], {"completed": 3, "total": 3})

    def test_stage_switch_resets_counts_then_new_stage_is_monotonic(self) -> None:
        records, _changed = update_child_progress(
            self.records,
            "bracketlapse-standby",
            completed=0,
            total=10,
            stage="video",
        )

        self.assertEqual(
            records[1]["progress"],
            {"stage": "video", "completed": 0, "total": 10},
        )
        records, changed = update_child_progress(
            records,
            "bracketlapse-standby",
            completed=4,
            total=8,
            stage="video",
        )
        self.assertTrue(changed)
        self.assertEqual(
            records[1]["progress"],
            {"stage": "video", "completed": 4, "total": 10},
        )

    def test_invalid_stage_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "无效的子进度阶段"):
            update_child_progress(
                self.records,
                "bracketlapse-standby",
                stage="encoding",
            )


if __name__ == "__main__":
    unittest.main()
