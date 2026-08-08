from __future__ import annotations

import unittest
from datetime import datetime

from timelapse_manager.ui.progress import task_progress_items, task_progress_label
from tests.progress_test_support import MANUAL_TASK, processing_state


class TaskProgressStageTests(unittest.TestCase):
    def test_waiting_capture_is_zero_with_countdown_and_no_subtasks(self) -> None:
        state = {
            "status": "running",
            "progress": {"main_stage": "waiting_capture"},
            "children": [
                {"role": "camera-timelapse", "pid": 101, "status": "running"},
                {"role": "bracketlapse-standby", "pid": 102, "status": "running"},
            ],
        }

        items = task_progress_items(
            MANUAL_TASK,
            state,
            now=datetime(2026, 7, 22, 11, 10),
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].label, "总体进度")
        self.assertEqual(items[0].detail, "等待拍摄")
        self.assertEqual(items[0].value, 0.0)
        self.assertEqual(items[0].value_text, "距开始 4小时50分")
        self.assertEqual(
            task_progress_label(
                MANUAL_TASK,
                state,
                now=datetime(2026, 7, 22, 11),
            ),
            "等待拍摄",
        )

    def test_capture_uses_schedule_and_hides_camera_and_pids(self) -> None:
        state = {
            "status": "running",
            "progress": {"main_stage": "capture"},
            "children": [
                {"role": "camera-timelapse", "pid": 101, "status": "running"},
                {
                    "role": "bracketlapse-standby",
                    "pid": 102,
                    "status": "running",
                    "progress": {"stage": "hdr", "completed": 1, "total": 4},
                },
                {
                    "role": "sunsetscore-resident",
                    "pid": 103,
                    "status": "running",
                    "progress": {
                        "stage": "sunset",
                        "completed": 1,
                        "total": 2,
                    },
                },
            ],
        }

        items = task_progress_items(
            MANUAL_TASK,
            state,
            now=datetime(2026, 7, 22, 17),
        )

        self.assertEqual(
            [item.key for item in items],
            ["overall", "subtask-hdr", "subtask-sunset"],
        )
        self.assertEqual(
            [item.label for item in items],
            ["总体进度", "HDR处理", "晚霞评分"],
        )
        self.assertTrue(all("PID" not in item.label for item in items))
        self.assertEqual(items[0].detail, "相机拍摄")
        self.assertAlmostEqual(items[0].value or 0, 0.25)
        self.assertEqual(
            task_progress_label(
                MANUAL_TASK,
                state,
                now=datetime(2026, 7, 22, 17),
            ),
            "相机拍摄 25%",
        )

    def test_waiting_processing_is_equal_weighted_and_can_retreat(self) -> None:
        state = processing_state(hdr=(4, 4), sunset=(1, 2))

        first = task_progress_items(MANUAL_TASK, state)[0]
        state["children"][0]["progress"]["total"] = 8
        second = task_progress_items(MANUAL_TASK, state)[0]

        self.assertEqual(first.detail, "等待处理")
        self.assertEqual(first.value, 0.75)
        self.assertEqual(second.value, 0.5)
        self.assertEqual(task_progress_label(MANUAL_TASK, state), "等待处理 50%")

    def test_caught_up_processing_is_indeterminate_until_video_starts(self) -> None:
        state = processing_state(hdr=(4, 4), sunset=(2, 2))

        items = task_progress_items(MANUAL_TASK, state)

        self.assertIsNone(items[0].value)
        self.assertEqual(items[0].value_text, "处理中")
        self.assertEqual([item.detail for item in items[1:]], ["已追平", "已追平"])
        self.assertEqual(task_progress_label(MANUAL_TASK, state), "等待处理")

    def test_video_progress_is_main_and_only_unfinished_sunset_remains(self) -> None:
        state = processing_state(hdr=(4, 4), sunset=(1, 3))
        state["progress"]["main_stage"] = "video_processing"
        state["children"][0]["progress"] = {
            "stage": "video",
            "completed": 2,
            "total": 5,
        }

        items = task_progress_items(MANUAL_TASK, state)

        self.assertEqual([item.key for item in items], ["overall", "subtask-sunset"])
        self.assertEqual(items[0].detail, "视频处理")
        self.assertEqual(items[0].value, 0.4)
        self.assertEqual(task_progress_label(MANUAL_TASK, state), "视频处理 40%")

    def test_legacy_video_is_indeterminate_then_complete_on_process_exit(self) -> None:
        state = {
            "status": "running",
            "phase": "视频导出",
            "progress": {"main_stage": "video_processing"},
            "children": [
                {
                    "role": "bracketlapse-standby",
                    "status": "running",
                    "progress": {"stage": "video", "completed": 0, "total": 0},
                }
            ],
        }

        self.assertIsNone(task_progress_items(MANUAL_TASK, state)[0].value)
        state["children"][0]["status"] = "completed"
        self.assertEqual(task_progress_items(MANUAL_TASK, state)[0].value, 1.0)
        self.assertEqual(task_progress_label(MANUAL_TASK, state), "视频处理 100%")


if __name__ == "__main__":
    unittest.main()
