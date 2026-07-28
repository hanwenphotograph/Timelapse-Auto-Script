from __future__ import annotations

import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.macos_source_app import (
    APP_NAME,
    BUNDLE_IDENTIFIER,
    EXECUTABLE_NAME,
    ICON_NAME,
    PythonEnvironment,
    build_source_application,
    current_environment,
)


class MacOSSourceApplicationTests(unittest.TestCase):
    def test_current_environment_preserves_virtualenv_launcher_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "base" / "python"
            launcher = root / "environment" / "bin" / "python"
            runtime.parent.mkdir(parents=True)
            launcher.parent.mkdir(parents=True)
            runtime.write_bytes(b"python")
            launcher.symlink_to(runtime)
            with (
                patch.object(sys, "base_prefix", str(root / "base")),
                patch.object(sys, "prefix", str(root / "environment")),
                patch.object(sys, "executable", str(launcher)),
            ):
                environment = current_environment()

            self.assertEqual(environment.runtime, runtime.resolve())
            self.assertEqual(environment.executable, launcher.absolute())

    def test_build_uses_the_selected_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self._environment(root)
            application = build_source_application(
                root,
                environment,
                sign=False,
            )

            contents = application / "Contents"
            executable = contents / "MacOS" / EXECUTABLE_NAME
            with (contents / "Info.plist").open("rb") as stream:
                info = plistlib.load(stream)

            self.assertEqual(application.name, APP_NAME)
            self.assertEqual(executable.read_bytes(), b"python-runtime")
            self.assertEqual(info["CFBundleIdentifier"], BUNDLE_IDENTIFIER)
            self.assertEqual(info["CFBundleIconFile"], ICON_NAME)
            self.assertFalse((contents / "bin").exists())
            self.assertFalse((contents / "lib").exists())
            self.assertFalse((contents / "MacOS" / "pyvenv.cfg").exists())

    def _environment(self, root: Path) -> PythonEnvironment:
        runtime = root / "python"
        runtime.write_bytes(b"python-runtime")
        executable = root / "environment" / "bin" / "python"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"environment-python")
        return PythonEnvironment(
            runtime=runtime,
            executable=executable,
            prefix=root / "environment",
        )


if __name__ == "__main__":
    unittest.main()
