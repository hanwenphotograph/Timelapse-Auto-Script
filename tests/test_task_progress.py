from __future__ import annotations

import unittest
from datetime import datetime

from timelapse_manager.ui.progress import (
    compact_timestamp,
    task_progress_items,
    task_progress_label,
)


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
        self.assertNotIn("█", label)

    def test_progress_items_start_with_overall_then_each_child(self) -> None:
        items = task_progress_items(
            self.task,
            {
                "status": "running",
                "phase": "视频导出",
                "children": [
                    {
                        "role": "camera-timelapse",
                        "pid": 101,
                        "status": "running",
                    },
                    {
                        "role": "bracketlapse-standby",
                        "pid": 102,
                        "status": "completed",
                    },
                ],
            },
            now=datetime(2026, 7, 22, 17),
        )

        self.assertEqual(
            [item.key for item in items],
            ["overall", "children-101", "children-102"],
        )
        self.assertEqual(items[0].label, "总体进度")
        self.assertAlmostEqual(items[0].value or 0, 0.25)
        self.assertAlmostEqual(items[1].value or 0, 0.25)
        self.assertEqual(items[2].value, 1.0)

    def test_unknown_running_subtask_uses_indeterminate_progress(self) -> None:
        items = task_progress_items(
            {"preset": "eternal"},
            {
                "status": "running",
                "phase": "永续拍摄中",
                "threads": {
                    "archive": {
                        "status": "running",
                        "phase": "等待归档批次",
                    }
                },
            },
        )

        self.assertIsNone(items[0].value)
        self.assertIsNone(items[1].value)
        self.assertEqual(items[1].label, "归档")

    def test_nested_subtask_progress_is_normalized(self) -> None:
        items = task_progress_items(
            {"preset": "eternal"},
            {
                "status": "running",
                "progress": {
                    "subtasks": {
                        "processor": {
                            "status": "running",
                            "progress": {"completed": 2, "total": 5},
                        }
                    }
                },
            },
        )

        self.assertAlmostEqual(items[1].value or 0, 0.4)

    def test_active_task_after_capture_window_is_not_reported_as_complete(self) -> None:
        state = {"status": "running", "phase": "等待后期处理"}

        items = task_progress_items(
            self.task,
            state,
            now=datetime(2026, 7, 22, 20, 10),
        )

        self.assertIsNone(items[0].value)
        self.assertEqual(
            task_progress_label(
                self.task,
                state,
                now=datetime(2026, 7, 22, 20, 10),
            ),
            "等待后期处理",
        )

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

        self.assertEqual(
            label, "持续运行 · 已归档 3 批 · 待归档 2 组 · 归档中 1 批 · 待处理 4 批"
        )

    def test_terminal_task_uses_terminal_status(self) -> None:
        self.assertEqual(
            task_progress_label(self.task, {"status": "completed"}), "已完成"
        )


if __name__ == "__main__":
    unittest.main()
