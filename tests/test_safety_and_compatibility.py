from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.config import ConfigManager
from timelapse_manager.errors import TaskError
from timelapse_manager.maintenance import cleanup_work_directory
from timelapse_manager.paths import AppPaths
from timelapse_manager.process_utils import resolve_command


class SafetyAndCompatibilityTests(unittest.TestCase):
    def test_cleanup_refuses_protected_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            protected = Path(temp_dir)
            (protected / "important.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(TaskError):
                cleanup_work_directory(
                    protected,
                    [],
                    lambda _message: None,
                    protected_paths=[protected],
                )
            self.assertTrue((protected / "important.txt").exists())

    def test_cleanup_only_keeps_configured_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work = Path(temp_dir) / "root" / "task"
            keep = work / "hdr_video"
            remove = work / "raw"
            keep.mkdir(parents=True)
            remove.mkdir()
            (remove / "frame.jpg").write_bytes(b"raw")
            cleanup_work_directory(work, ["hdr_video"], lambda _message: None)
            self.assertTrue(keep.is_dir())
            self.assertFalse(remove.exists())

    def test_quoted_command_with_arguments_resolves(self) -> None:
        command = f'"{sys.executable}" -c "print(123)"'
        resolved = resolve_command(command)
        self.assertEqual(Path(resolved[0]).resolve(), Path(sys.executable).resolve())
        self.assertEqual(resolved[1:], ["-c", "print(123)"])

    def test_legacy_environment_aliases_are_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ConfigManager(AppPaths.discover(Path(temp_dir)))
            manager.ensure()
            values = {
                "START_AT": "04:00",
                "END_AT": "08:00",
                "ETERNAL_BATCH_GROUPS": "42",
            }
            with patch.dict(os.environ, values, clear=False):
                os.environ.pop("MORNING_START_AT", None)
                os.environ.pop("MORNING_END_AT", None)
                loaded = manager.load()
            self.assertEqual(
                loaded.project["morning"], {"start_at": "04:00", "end_at": "08:00"}
            )
            self.assertEqual(loaded.project["eternal"]["batch_groups"], 42)


if __name__ == "__main__":
    unittest.main()
