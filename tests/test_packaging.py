from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_package import pyinstaller_command, platform_name
from timelapse_manager.paths import application_root
from timelapse_manager import release_entry
from timelapse_manager.release_entry import release_arguments
from timelapse_manager.ui.app import build_mode_label


class PackagingTests(unittest.TestCase):
    def test_debug_command_keeps_console_and_source_entrypoint(self) -> None:
        command = pyinstaller_command("debug", Path("/tmp/debug-build"))
        self.assertIn("--console", command)
        self.assertNotIn("--windowed", command)
        self.assertTrue(command[-1].endswith("timelapse.py"))

    def test_release_command_is_windowed_and_uses_release_entrypoint(self) -> None:
        command = pyinstaller_command("release", Path("/tmp/release-build"))
        self.assertIn("--windowed", command)
        self.assertNotIn("--console", command)
        self.assertTrue(command[-1].endswith("release_entry.py"))

    def test_platform_names_are_normalized(self) -> None:
        self.assertEqual(platform_name("Darwin"), "mac")
        self.assertEqual(platform_name("Windows"), "win")

    def test_release_entry_defaults_to_gui_but_preserves_worker_arguments(self) -> None:
        self.assertEqual(release_arguments([]), ["gui"])
        self.assertEqual(release_arguments(["_worker", "--task", "task-id"]), [
            "_worker",
            "--task",
            "task-id",
        ])

    def test_release_entry_invokes_cli_with_effective_arguments(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("timelapse_manager.release_entry.cli_main", return_value=0) as main,
        ):
            self.assertEqual(release_entry.main([]), 0)
        main.assert_called_once_with(["gui"])

    def test_frozen_macos_application_uses_directory_next_to_bundle(self) -> None:
        executable = Path(
            "/tmp/TimelapseManager/TimelapseManager.app/Contents/MacOS/TimelapseManager"
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "platform", "darwin"),
            patch.object(sys, "executable", str(executable)),
        ):
            self.assertEqual(
                application_root(), Path("/tmp/TimelapseManager").resolve()
            )

    def test_build_label_follows_release_environment(self) -> None:
        with patch.dict(os.environ, {"TIMELAPSE_MANAGER_BUILD_MODE": "release"}):
            self.assertEqual(build_mode_label(), "Release")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(build_mode_label(), "Debug")


if __name__ == "__main__":
    unittest.main()
