from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.dependency_manager.installation import (
    PACKAGE_URLS,
    DependencyInstaller,
    InstallPlan,
)
from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.dependency_manager.progress import InstallProgressTracker
from timelapse_manager.dependency_manager.sunset_resources import (
    SunsetResourceSnapshot,
)
from timelapse_manager.dependency_manager.system_install import (
    expand_formula_install_command,
)


class InstallProgressTests(unittest.TestCase):
    def test_generic_installer_percentage_is_reported(self) -> None:
        tracker = InstallProgressTracker()

        self.assertEqual(tracker.consume("Receiving objects: 42%"), 0.42)

    def test_sunset_downloads_are_weighted_by_artifact_size(self) -> None:
        megabyte = 1024**2
        tracker = InstallProgressTracker(
            (("model.gguf", 100 * megabyte), ("projector.gguf", 50 * megabyte))
        )

        tracker.consume("开始下载 runtime.zip（50.0 MB）")
        self.assertAlmostEqual(tracker.consume("下载进度 runtime.zip：50%"), 0.125)
        self.assertAlmostEqual(tracker.consume("下载完成：runtime.zip"), 0.25)
        self.assertAlmostEqual(tracker.consume("下载进度 model.gguf：50%"), 0.5)
        tracker.consume("正在校验：model.gguf")
        self.assertAlmostEqual(tracker.consume("下载完成：projector.gguf"), 1.0)

    def test_installer_forwards_parsed_progress_and_completion(self) -> None:
        installer = DependencyInstaller(Path.cwd())
        plan = InstallPlan(
            (sys.executable, "-c", "print('Downloading: 25%')"),
            "test",
        )
        values = []

        installer.execute(plan, on_progress=values.append)

        self.assertEqual(values, [0.25, 1.0])


class DependencyInstallationTests(unittest.TestCase):
    def test_source_install_uses_the_private_python_environment(self) -> None:
        installer = DependencyInstaller(Path.cwd())
        plan = installer.plan("python:sunsetscore", {})

        assert plan is not None
        paths = DependencyPaths.discover(Path.cwd())
        self.assertEqual(plan.command[:3], (str(paths.uv_executable), "pip", "install"))
        self.assertEqual(
            plan.command[plan.command.index("--python") + 1],
            str(paths.python_executable),
        )
        self.assertEqual(plan.bootstrap, "python")
        self.assertEqual(plan.command[-1], PACKAGE_URLS["sunsetscore"])

    def test_sunset_prepare_uses_public_cli(self) -> None:
        snapshot = SunsetResourceSnapshot(
            ("/tools/sunsetscore",),
            {},
            (("model.gguf", 100), ("projector.gguf", 50)),
        )
        installer = DependencyInstaller(Path.cwd())
        with patch(
            "timelapse_manager.dependency_manager.installation.query_sunset_resources",
            return_value=snapshot,
        ):
            plan = installer.plan("sunset:prepare", {"sunsetscore": "sunsetscore"})

        assert plan is not None
        self.assertEqual(
            plan.command,
            ("/tools/sunsetscore", "runtime", "prepare"),
        )
        self.assertEqual(plan.progress_sizes, snapshot.artifacts)

    def test_formula_install_plans_force_private_bottles(self) -> None:
        installer = DependencyInstaller(Path.cwd())

        gphoto = installer.plan("system:gphoto2", {})
        deflicker = installer.plan("tool:simple-deflicker", {})

        assert gphoto is not None
        assert deflicker is not None
        self.assertIn("--force-bottle", gphoto.command)
        self.assertIn("--force-bottle", deflicker.command)

    def test_formula_dependencies_are_explicit_force_bottle_targets(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            "gettext\nlibusb\n",
            "",
        )

        command = expand_formula_install_command(
            ("/private/brew", "install", "--force-bottle", "gphoto2"),
            {"HOME": "/private/home"},
            run=lambda *_args, **_kwargs: completed,
        )

        self.assertEqual(
            command,
            (
                "/private/brew",
                "install",
                "--force-bottle",
                "gettext",
                "libusb",
                "gphoto2",
            ),
        )


if __name__ == "__main__":
    unittest.main()
