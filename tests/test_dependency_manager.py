from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.bracketlapse import BracketlapseAvailability
from timelapse_manager.dependency_manager.inspection import DependencyInspector
from timelapse_manager.dependency_manager.installation import (
    PACKAGE_URLS,
    DependencyInstaller,
    InstallPlan,
)
from timelapse_manager.dependency_manager.models import DependencyBuildInfo
from timelapse_manager.dependency_manager.progress import InstallProgressTracker
from timelapse_manager.dependency_manager.sunset_resources import (
    SunsetResourceSnapshot,
    inspect_sunset_resources,
)
from timelapse_manager.sunset_score.availability import SunsetScoreAvailability


class SunsetResourceTests(unittest.TestCase):
    def test_public_status_reports_resources_separately(self) -> None:
        availability = SunsetScoreAvailability(("/tools/sunsetscore",), "0.10.0")
        completed = subprocess.CompletedProcess(
            [],
            0,
            (
                '{"application_version":"0.10.0","resources":{'
                '"runtime":{"state":"ready","detail":"CPU"},'
                '"model":{"state":"ready","detail":"model",'
                '"artifact":{"filename":"model.gguf","size":100}},'
                '"projector":{"state":"ready","detail":"projector",'
                '"artifact":{"filename":"projector.gguf","size":50}}}}'
            ),
            "",
        )

        results = inspect_sunset_resources(
            availability, run=lambda *_args, **_kwargs: completed
        )

        self.assertEqual({state for state, _detail in results.values()}, {"ready"})
        self.assertIn("CPU", results["sunset_runtime"][1])

    def test_invalid_public_status_is_reported_as_issue(self) -> None:
        availability = SunsetScoreAvailability(("/tools/sunsetscore",), "0.10.0")
        completed = subprocess.CompletedProcess(
            [], 0, '{"application_version":"0.10.0","resources":{}}', ""
        )

        state, detail = inspect_sunset_resources(
            availability, run=lambda *_args, **_kwargs: completed
        )["sunset_model"]

        self.assertEqual(state, "issue")
        self.assertIn("状态无效", detail)


class DependencyInspectionTests(unittest.TestCase):
    def test_parent_and_child_dependencies_keep_catalog_order(self) -> None:
        sunset = SunsetScoreAvailability(("/tools/sunsetscore",), "0.10.0")
        bracket = BracketlapseAvailability(("/tools/bracketlapse",), "0.2.0")
        resources = {
            "sunset_runtime": ("missing", "runtime missing"),
            "sunset_model": ("ready", "model ready"),
            "sunset_projector": ("missing", "projector missing"),
        }
        with (
            patch(
                "timelapse_manager.dependency_manager.inspection.resolve_command",
                side_effect=lambda primary, fallback=None: [f"/tools/{primary}"],
            ),
            patch(
                "timelapse_manager.dependency_manager.inspection.detect_sunset_score",
                return_value=sunset,
            ),
            patch(
                "timelapse_manager.dependency_manager.inspection.detect_bracketlapse",
                return_value=bracket,
            ),
            patch(
                "timelapse_manager.dependency_manager.inspection.inspect_sunset_resources",
                return_value=resources,
            ),
            patch(
                "timelapse_manager.dependency_manager.inspection.inspect_build_info",
                side_effect=lambda command: DependencyBuildInfo(
                    "0.10.0" if "sunsetscore" in command[0] else "0.2.0",
                    "main",
                    "2026-08-08T12:30:00Z",
                    "abc123",
                ),
            ),
        ):
            progress = []
            statuses = DependencyInspector().inspect(
                {},
                lambda completed, total, name: progress.append(
                    (completed, total, name)
                ),
            )

        self.assertEqual(statuses[0].spec.identifier, "camera")
        self.assertEqual(statuses[1].spec.parent_id, "camera")
        self.assertEqual(statuses[6].state, "ready")
        self.assertEqual(statuses[7].spec.parent_id, "sunsetscore")
        self.assertEqual(statuses[8].state, "ready")
        self.assertEqual(statuses[2].build_info.branch, "main")
        self.assertEqual(statuses[6].build_info.build_time, "2026-08-08T12:30:00Z")
        self.assertEqual([item[0] for item in progress], list(range(1, 11)))
        self.assertTrue(all(item[1] == 10 for item in progress))


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
    def test_source_install_uses_the_active_python_environment(self) -> None:
        installer = DependencyInstaller(Path.cwd())
        with patch.object(sys, "frozen", False, create=True):
            plan = installer.plan("python:sunsetscore", {})

        assert plan is not None
        self.assertEqual(plan.command[:4], (sys.executable, "-m", "pip", "install"))
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


if __name__ == "__main__":
    unittest.main()
