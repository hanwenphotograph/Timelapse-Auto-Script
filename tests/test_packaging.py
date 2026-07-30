from __future__ import annotations

import os
import plistlib
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from scripts.build_package import (
    _archive_package,
    _stage_application,
    platform_name,
    pyinstaller_command,
)
from scripts.macos_package import (
    APPLICATION_VERSION,
    BUNDLE_IDENTIFIER,
    finalize_application,
)
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

    def test_macos_release_uses_stable_bundle_metadata(self) -> None:
        command = pyinstaller_command(
            "release", Path("/tmp/release-build"), system="Darwin"
        )
        self.assertEqual(
            command[command.index("--osx-bundle-identifier") + 1],
            BUNDLE_IDENTIFIER,
        )
        with tempfile.TemporaryDirectory() as temporary:
            application = Path(temporary) / "TimelapseManager.app"
            plist_path = application / "Contents" / "Info.plist"
            plist_path.parent.mkdir(parents=True)
            with plist_path.open("wb") as stream:
                plistlib.dump({"CFBundleShortVersionString": "0.0.0"}, stream)

            with patch("scripts.macos_package.subprocess.run") as run:
                finalize_application(application)

            with plist_path.open("rb") as stream:
                info = plistlib.load(stream)
            self.assertEqual(info["CFBundleIdentifier"], BUNDLE_IDENTIFIER)
            self.assertEqual(info["CFBundleShortVersionString"], APPLICATION_VERSION)
            self.assertEqual(info["CFBundleVersion"], APPLICATION_VERSION)
            self.assertEqual(run.call_count, 2)

    @unittest.skipUnless(sys.platform == "darwin", "macOS archive behavior")
    def test_macos_portable_archive_preserves_framework_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "dist" / "TimelapseManager.app"
            versions = (
                source / "Contents" / "Frameworks" / "Python.framework" / "Versions"
            )
            current = versions / "Current"
            (versions / "3.10").mkdir(parents=True)
            current.symlink_to("3.10", target_is_directory=True)
            package_dir = root / "package" / "TimelapseManager"

            _stage_application(source, package_dir, "release", "mac")
            staged = (
                package_dir
                / "TimelapseManager.app"
                / "Contents"
                / "Frameworks"
                / "Python.framework"
                / "Versions"
                / "Current"
            )
            self.assertTrue(staged.is_symlink())

            archive = _archive_package(package_dir, root / "release", "mac")
            with ZipFile(archive) as zipped:
                member = zipped.getinfo(
                    "TimelapseManager/TimelapseManager.app/Contents/Frameworks/"
                    "Python.framework/Versions/Current"
                )
                self.assertTrue(stat.S_ISLNK(member.external_attr >> 16))
                self.assertEqual(zipped.read(member), b"3.10")

    def test_release_entry_defaults_to_gui_but_preserves_worker_arguments(self) -> None:
        self.assertEqual(release_arguments([]), ["gui"])
        self.assertEqual(
            release_arguments(["_worker", "--task", "task-id"]),
            [
                "_worker",
                "--task",
                "task-id",
            ],
        )

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
