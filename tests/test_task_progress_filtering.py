from __future__ import annotations

import unittest
from datetime import datetime

from timelapse_manager.ui.progress import (
    compact_timestamp,
    task_progress_items,
    task_progress_label,
)
from tests.progress_test_support import MANUAL_TASK


class TaskProgressFilteringTests(unittest.TestCase):
    def test_terminal_filtering_hides_success_and_keeps_failed_feature(self) -> None:
        children = [
            {"role": "camera-timelapse", "status": "failed"},
            {"role": "bracketlapse-standby", "status": "failed"},
            {"role": "sunsetscore-resident", "status": "completed"},
        ]

        completed = task_progress_items(
            MANUAL_TASK,
            {"status": "completed", "children": children},
        )
        stopped = task_progress_items(
            MANUAL_TASK,
            {"status": "stopped", "children": children},
        )
        failed = task_progress_items(
            MANUAL_TASK,
            {"status": "failed", "children": children},
        )

        self.assertEqual(len(completed), 1)
        self.assertEqual(len(stopped), 1)
        self.assertEqual([item.label for item in failed], ["总体进度", "HDR处理"])
        self.assertEqual(failed[1].status, "failed")

    def test_eternal_only_shows_current_batch_and_score_and_switches_stage(
        self,
    ) -> None:
        state = {
            "status": "running",
            "children": [
                {"role": "camera-timelapse-eternal", "status": "running"},
                {"role": "bracketlapse-batch-1", "status": "completed"},
                {
                    "role": "bracketlapse-batch-2",
                    "status": "running",
                    "progress": {"stage": "hdr", "completed": 2, "total": 4},
                },
                {
                    "role": "sunsetscore-resident",
                    "status": "running",
                    "progress": {
                        "stage": "sunset",
                        "completed": 1,
                        "total": 2,
                    },
                },
            ],
        }

        hdr_items = task_progress_items({"preset": "eternal"}, state)
        state["children"][2]["progress"] = {
            "stage": "video",
            "completed": 3,
            "total": 10,
        }
        video_items = task_progress_items({"preset": "eternal"}, state)

        self.assertEqual(
            [item.label for item in hdr_items],
            ["持续拍摄", "批次 2", "晚霞评分"],
        )
        self.assertEqual(hdr_items[1].value_text, "2/4")
        self.assertEqual(video_items[1].value, 0.3)
        self.assertIsNone(video_items[1].value_text)

    def test_legacy_stage_inference_uses_live_processes_and_phase(self) -> None:
        before = {
            "status": "running",
            "phase": "守护拍摄计划",
            "children": [
                {"role": "camera-timelapse", "status": "running"},
                {"role": "bracketlapse-standby", "status": "running"},
            ],
        }
        processing = {
            "status": "running",
            "phase": "去闪处理",
            "children": [
                {"role": "camera-timelapse", "status": "completed"},
                {"role": "bracketlapse-standby", "status": "running"},
            ],
        }

        self.assertEqual(
            task_progress_items(
                MANUAL_TASK,
                before,
                now=datetime(2026, 7, 22, 15),
            )[0].detail,
            "等待拍摄",
        )
        self.assertEqual(
            task_progress_items(MANUAL_TASK, processing)[0].detail,
            "等待处理",
        )
        processing["phase"] = "视频导出"
        self.assertEqual(
            task_progress_items(MANUAL_TASK, processing)[0].detail,
            "视频处理",
        )

    def test_compact_timestamp_and_terminal_table_labels(self) -> None:
        source = "2026-07-22T11:09:04+08:00"
        self.assertEqual(
            compact_timestamp(source),
            datetime.fromisoformat(source).astimezone().strftime("%Y-%m-%d %H:%M"),
        )
        self.assertEqual(
            task_progress_label(MANUAL_TASK, {"status": "completed"}),
            "已完成",
        )
        self.assertEqual(
            task_progress_label(
                {"preset": "eternal"},
                {
                    "status": "running",
                    "progress": {"eternal_batches": 3, "eternal_queue": 2},
                },
            ),
            "持续运行 · 已归档 3 批 · 待处理 2 批",
        )


if __name__ == "__main__":
    unittest.main()
