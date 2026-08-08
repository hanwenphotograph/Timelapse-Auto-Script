from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from timelapse_manager.progress_compat import TaskLogProgressReader


class TaskLogProgressReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.temp.name) / "task.log"
        self.reader = TaskLogProgressReader()
        self.state = {
            "status": "running",
            "started_at": "2026-08-08T19:18:15+08:00",
            "runner_pid": 100,
            "children": [
                {"role": "bracketlapse-standby", "status": "running"},
                {"role": "sunsetscore-resident", "status": "running"},
            ],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_recovers_hdr_and_sunset_counts_without_mutating_state(self) -> None:
        self._write_lines(
            "任务工作进程启动，模式=manual，PID=100",
            "[camera-timelapse] Starting capture round 0003",
            self._hdr_event(2),
            self._sunset_event("session-1", 1, 1, 3),
        )

        enriched = self.reader.enrich_state(self.state, self.log_path)

        self.assertNotIn("progress", self.state["children"][0])
        self.assertEqual(
            enriched["children"][0]["progress"],
            {"stage": "hdr", "completed": 2, "total": 3},
        )
        self.assertEqual(
            enriched["children"][1]["progress"],
            {"stage": "sunset", "completed": 2, "total": 3},
        )

    def test_reads_only_appended_lines_and_allows_ratio_to_retreat(self) -> None:
        self._write_lines(
            "[camera-timelapse] Starting capture round 0002",
            self._hdr_event(1),
        )
        first = self.reader.enrich_state(self.state, self.log_path)

        self._append_lines("[camera-timelapse] Starting capture round 0004")
        second = self.reader.enrich_state(self.state, self.log_path)

        self.assertEqual(
            first["children"][0]["progress"],
            {"stage": "hdr", "completed": 1, "total": 2},
        )
        self.assertEqual(
            second["children"][0]["progress"],
            {"stage": "hdr", "completed": 1, "total": 4},
        )

    def test_latest_worker_marker_resets_counts_from_an_older_run(self) -> None:
        self._write_lines(
            "任务工作进程启动，模式=manual，PID=99",
            "[camera-timelapse] Starting capture round 0100",
            self._hdr_event(99),
            "任务工作进程启动，模式=manual，PID=100",
            "[camera-timelapse] Starting capture round 0002",
            self._hdr_event(1),
        )

        enriched = self.reader.enrich_state(self.state, self.log_path)

        self.assertEqual(
            enriched["children"][0]["progress"],
            {"stage": "hdr", "completed": 1, "total": 2},
        )

    def test_sunset_progress_aggregates_independent_sessions(self) -> None:
        self._write_lines(
            self._sunset_event("session-1", 2, 0, 3),
            self._sunset_event("session-1", 3, 0, 4),
            self._sunset_event("session-2", 1, 0, 2),
        )

        enriched = self.reader.enrich_state(self.state, self.log_path)

        self.assertEqual(
            enriched["children"][1]["progress"],
            {"stage": "sunset", "completed": 4, "total": 6},
        )

    def test_video_events_enrich_only_the_display_copy(self) -> None:
        self._write_lines(
            self._video_event("video_started", 0, 8),
            self._video_event("video_progress", 3, 8),
        )

        enriched = self.reader.enrich_state(self.state, self.log_path)

        self.assertNotIn("progress", self.state)
        self.assertNotIn("progress", self.state["children"][0])
        self.assertEqual(enriched["progress"]["main_stage"], "video_processing")
        self.assertEqual(
            enriched["children"][0]["progress"],
            {"stage": "video", "completed": 3, "total": 8},
        )

    def test_human_video_start_falls_back_to_indeterminate_counts(self) -> None:
        self._write_lines(
            "[bracketlapse-standby] Creating video from hdr_deflick frames."
        )

        enriched = self.reader.enrich_state(self.state, self.log_path)

        self.assertEqual(enriched["progress"]["main_stage"], "video_processing")
        self.assertEqual(
            enriched["children"][0]["progress"],
            {"stage": "video", "completed": 0, "total": 0},
        )

    def _write_lines(self, *lines: str) -> None:
        self.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _append_lines(self, *lines: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    @staticmethod
    def _hdr_event(frame_number: int) -> str:
        value = {"event": "hdr_ready", "frame_number": frame_number}
        return "[bracketlapse-standby] BRACKETLAPSE_EVENT " + json.dumps(value)

    @staticmethod
    def _sunset_event(
        session: str,
        successful: int,
        failed: int,
        sampled: int,
    ) -> str:
        value = {
            "event": "scan_complete",
            "session": session,
            "successful_count": successful,
            "failed_count": failed,
            "sampled_count": sampled,
        }
        return "[sunsetscore-resident] " + json.dumps(value)

    @staticmethod
    def _video_event(event: str, completed: int, total: int) -> str:
        value = {
            "event": event,
            "path": "/tmp/output.mp4",
            "completed": completed,
            "total": total,
        }
        return "[bracketlapse-standby] BRACKETLAPSE_EVENT " + json.dumps(value)


if __name__ == "__main__":
    unittest.main()
