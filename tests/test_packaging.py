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


ROOT = Path(__file__).resolve().parents[1]


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

    def test_build_commands_use_platform_native_icons(self) -> None:
        suffixes = {"Windows": ".ico", "Darwin": ".icns", "Linux": ".png"}
        for system, suffix in suffixes.items():
            command = pyinstaller_command(
                "release",
                Path("/tmp/icon-build"),
                system=system,
            )
            icon = Path(command[command.index("--icon") + 1])
            bundled = command[command.index("--add-data") + 1]
            self.assertEqual(icon.suffix, suffix)
            self.assertTrue(icon.is_file())
            self.assertIn("timelapse-manager.png", bundled)

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

    def test_macos_launcher_closes_its_terminal_after_gui_exit(self) -> None:
        launcher = (ROOT / "start_gui.command").read_text(encoding="utf-8")

        self.assertIn("schedule_terminal_close", launcher)
        self.assertIn("/usr/bin/nohup /usr/bin/osascript", launcher)
        self.assertIn("close terminalTab", launcher)
        self.assertIn("macos_source_app.py", launcher)
        self.assertIn('if [ "$exit_code" -eq 78 ]', launcher)
        self.assertNotIn('exec "./TimelapseManager" gui', launcher)
        self.assertNotIn('exec "$GUI_PYTHON" "./timelapse.py" gui', launcher)
        self.assertNotIn('"$GUI_PYTHON" "./timelapse.py" gui', launcher)

    def test_windows_launcher_does_not_pause_after_gui_exit(self) -> None:
        launcher = (ROOT / "start_gui.bat").read_text(encoding="utf-8")
        finished = launcher.split(":finished", 1)[1].split(":failed", 1)[0]

        self.assertNotIn("pause", finished.lower())
        self.assertIn("exit /b %LAUNCH_EXIT_CODE%", finished)


if __name__ == "__main__":
    unittest.main()
