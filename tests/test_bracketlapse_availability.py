from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.bracketlapse import (
    detect_bracketlapse,
    parse_hdr_ready,
    parse_video_progress,
)


class BracketlapseAvailabilityTests(unittest.TestCase):
    @patch(
        "timelapse_manager.bracketlapse.availability.resolve_command",
        return_value=["/tools/bracketlapse"],
    )
    def test_supported_version_is_enabled(self, _resolve) -> None:
        completed = subprocess.CompletedProcess([], 0, "bracketlapse 0.2.0\n", "")

        result = detect_bracketlapse(
            "bracketlapse", run=lambda *_args, **_kwargs: completed
        )

        self.assertTrue(result.enabled)
        self.assertEqual(result.version, "0.2.0")

    @patch(
        "timelapse_manager.bracketlapse.availability.resolve_command",
        return_value=["/tools/bracketlapse"],
    )
    def test_older_version_is_rejected(self, _resolve) -> None:
        completed = subprocess.CompletedProcess([], 0, "bracketlapse 0.1.0\n", "")

        result = detect_bracketlapse(
            "bracketlapse", run=lambda *_args, **_kwargs: completed
        )

        self.assertFalse(result.enabled)
        self.assertIn("最低要求 0.2.0", result.reason)

    def test_hdr_event_path_must_stay_in_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            hdr_dir = work_dir / "hdr_enfuse"
            hdr_dir.mkdir()
            frame = hdr_dir / "frame.jpg"
            frame.write_bytes(b"image")
            event = "BRACKETLAPSE_EVENT " + json.dumps(
                {"event": "hdr_ready", "frame_number": 1, "path": str(frame)}
            )

            parsed = parse_hdr_ready(event, work_dir)

            assert parsed is not None
            self.assertEqual(parsed.path, frame.resolve())
            outside = work_dir / "outside.jpg"
            outside.write_bytes(b"image")
            unsafe = "BRACKETLAPSE_EVENT " + json.dumps(
                {"event": "hdr_ready", "frame_number": 2, "path": str(outside)}
            )
            with self.assertRaisesRegex(ValueError, "路径不安全"):
                parse_hdr_ready(unsafe, work_dir)

    def test_video_events_validate_counts_and_absolute_safe_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            output = work_dir / "hdr_video" / "timelapse.mp4"
            line = "BRACKETLAPSE_EVENT " + json.dumps(
                {
                    "event": "video_progress",
                    "path": str(output),
                    "completed": 3,
                    "total": 8,
                }
            )

            parsed = parse_video_progress(line, work_dir)

            assert parsed is not None
            self.assertEqual(parsed.event, "video_progress")
            self.assertEqual((parsed.completed, parsed.total), (3, 8))
            invalid = "BRACKETLAPSE_EVENT " + json.dumps(
                {
                    "event": "video_completed",
                    "path": str(output),
                    "completed": 7,
                    "total": 8,
                }
            )
            with self.assertRaisesRegex(ValueError, "完成全部帧"):
                parse_video_progress(invalid, work_dir)


if __name__ == "__main__":
    unittest.main()
