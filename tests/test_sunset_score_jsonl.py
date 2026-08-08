from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from timelapse_manager.sunset_score.jsonl_client import SunsetScoreJsonlClient
from timelapse_manager.sunset_score.jsonl_protocol import (
    decode_event,
    encode_request,
    ready_error,
    scan_progress,
)
from timelapse_manager.sunset_score.progress import SunsetProgressTracker


class SunsetScoreJsonlTests(unittest.TestCase):
    def test_client_uses_only_the_public_cli(self) -> None:
        runtime = SimpleNamespace()

        client = SunsetScoreJsonlClient(
            runtime,  # type: ignore[arg-type]
            ("/tools/sunsetscore",),
            interval=7,
            application_version="0.10.0",
        )

        self.assertEqual(
            client.argv,
            ["/tools/sunsetscore", "--serve-jsonl", "--interval", "7"],
        )

    def test_request_and_ready_event_follow_versioned_protocol(self) -> None:
        line = encode_request(
            4,
            "scan",
            session_id="task-1",
            directory="/photos/hdr_enfuse",
        )

        self.assertEqual(
            json.loads(line),
            {
                "id": 4,
                "command": "scan",
                "session": "task-1",
                "directory": "/photos/hdr_enfuse",
            },
        )
        event = decode_event(
            '{"event":"ready","protocol_version":1,"application_version":"0.10.0"}'
        )
        assert event is not None
        self.assertEqual(ready_error(event, "0.10.0"), "")
        self.assertIn(
            "协议版本", ready_error(event | {"protocol_version": 2}, "0.10.0")
        )

    def test_scan_progress_validates_processed_and_total_counts(self) -> None:
        self.assertEqual(
            scan_progress(
                {
                    "event": "scan_complete",
                    "successful_count": 3,
                    "failed_count": 1,
                    "sampled_count": 5,
                }
            ),
            (4, 5),
        )
        self.assertIsNone(
            scan_progress(
                {
                    "event": "scan_complete",
                    "successful_count": 6,
                    "failed_count": 0,
                    "sampled_count": 5,
                }
            )
        )

    def test_tracker_updates_submission_and_response_counts(self) -> None:
        runtime = SimpleNamespace(set_child_progress=Mock(), log=Mock())
        tracker = SunsetProgressTracker(runtime, interval=2)  # type: ignore[arg-type]
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "frame-1.jpg").write_bytes(b"image")
            tracker.submitted("session-a", directory)
            (directory / "frame-2.jpg").write_bytes(b"image")
            (directory / "frame-3.jpg").write_bytes(b"image")
            tracker.submitted("session-a", directory)

        tracker.response(
            "session-a",
            {
                "event": "scan_complete",
                "successful_count": 1,
                "failed_count": 0,
                "sampled_count": 2,
            },
        )

        self.assertEqual(runtime.set_child_progress.call_count, 3)
        self.assertEqual(
            runtime.set_child_progress.call_args.kwargs,
            {
                "completed": 1,
                "total": 2,
                "stage": "sunset",
                "phase": "晚霞评分",
            },
        )


if __name__ == "__main__":
    unittest.main()
