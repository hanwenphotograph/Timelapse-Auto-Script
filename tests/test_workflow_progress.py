from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call

from timelapse_manager.workflows.scheduled_support import (
    CaptureProgress,
    WorkSpec,
    bracket_output_handler,
    camera_output_handler,
)


class WorkflowProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp.name)
        self.spec = WorkSpec(
            "手动",
            self.work_dir,
            "2026-08-08",
            "15:00",
            "2026-08-08",
            "21:00",
        )
        self.runtime = Mock()
        self.progress = CaptureProgress()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_capture_rounds_update_hdr_total(self) -> None:
        handle = camera_output_handler(
            self.runtime,
            self.spec,
            self.progress,
            hdr_role="bracketlapse-standby",
        )

        handle("Starting capture round 0001")
        handle("Starting capture round 0002")

        self.assertEqual(self.progress.rounds, 2)
        self.assertEqual(
            self.runtime.set_child_progress.call_args_list,
            [
                call(
                    "bracketlapse-standby",
                    total=1,
                    stage="hdr",
                    phase="HDR处理",
                ),
                call(
                    "bracketlapse-standby",
                    total=2,
                    stage="hdr",
                    phase="HDR处理",
                ),
            ],
        )
        self.runtime.set_main_stage.assert_called_once_with("capture")

    def test_hdr_ready_updates_completed_count(self) -> None:
        hdr_dir = self.work_dir / "hdr_enfuse"
        hdr_dir.mkdir()
        image = hdr_dir / "frame-0001.jpg"
        image.write_bytes(b"image")
        ready = Mock()
        handle = bracket_output_handler(
            self.runtime,
            self.spec,
            ready,
            progress=self.progress,
            child_role="bracketlapse-standby",
        )
        event = "BRACKETLAPSE_EVENT " + json.dumps(
            {
                "event": "hdr_ready",
                "frame_number": 1,
                "path": str(image),
            }
        )

        handle(event)

        self.assertEqual(self.progress.hdr_completed, 1)
        self.assertEqual(self.progress.rounds, 1)
        self.runtime.set_child_progress.assert_called_once_with(
            "bracketlapse-standby",
            completed=1,
            stage="hdr",
            phase="HDR处理",
        )
        ready.assert_called_once_with()

    def test_video_event_switches_main_and_child_stage(self) -> None:
        output = self.work_dir / "hdr_video" / "timelapse.mp4"
        event = "BRACKETLAPSE_EVENT " + json.dumps(
            {
                "event": "video_progress",
                "path": str(output),
                "completed": 2,
                "total": 5,
            }
        )
        handle = bracket_output_handler(self.runtime, self.spec)

        handle(event)

        self.runtime.set_main_stage.assert_called_once_with("video_processing")
        self.runtime.set_child_progress.assert_called_once_with(
            "bracketlapse-standby",
            completed=2,
            total=5,
            stage="video",
            phase="视频处理",
        )
        self.runtime.set_phase.assert_called_once_with("视频导出", str(self.work_dir))

    def test_human_video_log_uses_indeterminate_fallback(self) -> None:
        handle = bracket_output_handler(self.runtime, self.spec)

        handle("Creating video from hdr_deflick frames.")

        self.runtime.set_main_stage.assert_called_once_with("video_processing")
        self.runtime.set_child_progress.assert_called_once_with(
            "bracketlapse-standby",
            completed=0,
            total=0,
            stage="video",
            phase="视频处理",
        )


if __name__ == "__main__":
    unittest.main()
