from __future__ import annotations

import unittest
from datetime import datetime

from timelapse_manager.ui.progress import compact_timestamp, task_progress_label


class TaskProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = {
            "preset": "manual",
            "capture": {
                "start_date": "2026-07-22",
                "start_at": "16:00",
                "end_date": "2026-07-22",
                "end_at": "20:00",
            },
        }

    def test_running_task_reports_time_until_capture_starts(self) -> None:
        label = task_progress_label(
            self.task,
            {"status": "running", "phase": "守护拍摄计划"},
            now=datetime(2026, 7, 22, 11, 10),
        )

        self.assertEqual(label, "距开始 4小时50分")

    def test_compact_timestamp_hides_seconds_and_timezone(self) -> None:
        self.assertEqual(
            compact_timestamp("2026-07-22T11:09:04+08:00"),
            "2026-07-22 11:09",
        )

    def test_running_task_reports_capture_percentage(self) -> None:
        label = task_progress_label(
            self.task,
            {"status": "running", "phase": "正在拍摄"},
            now=datetime(2026, 7, 22, 17),
        )

        self.assertIn("25%", label)
        self.assertNotIn("·", label)

    def test_eternal_task_reports_recorded_queue_progress(self) -> None:
        label = task_progress_label(
            {"preset": "eternal"},
            {
                "status": "running",
                "progress": {
                    "eternal_batches": 3,
                    "eternal_pending_groups": 2,
                    "eternal_archives": 1,
                    "eternal_queue": 4,
                },
            },
        )

        self.assertEqual(label, "持续运行 · 已归档 3 批 · 待归档 2 组 · 归档中 1 批 · 待处理 4 批")

    def test_terminal_task_uses_terminal_status(self) -> None:
        self.assertEqual(
            task_progress_label(self.task, {"status": "completed"}), "已完成"
        )


if __name__ == "__main__":
    unittest.main()
