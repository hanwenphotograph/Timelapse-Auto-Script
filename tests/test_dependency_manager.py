from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.bracketlapse import BracketlapseAvailability
from timelapse_manager.dependency_manager.inspection import DependencyInspector
from timelapse_manager.dependency_manager.health import CommandProbe
from timelapse_manager.dependency_manager.models import DependencyBuildInfo
from timelapse_manager.dependency_manager.sunset_resources import (
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
                side_effect=lambda primary, fallback=None, **_kwargs: [
                    f"/tools/{primary}"
                ],
            ),
            patch(
                "timelapse_manager.dependency_manager.inspection.probe_command",
                return_value=CommandProbe(True, "ok"),
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
                side_effect=lambda command, **_kwargs: DependencyBuildInfo(
                    "0.10.0" if "sunsetscore" in command[0] else "0.2.0",
                    "dev_deflick" if "bracketlapse" in command[0] else "main",
                    "2026-08-08T12:30:00Z",
                    "abc123",
                ),
            ),
            patch(
                "timelapse_manager.dependency_manager.inspection.matching_build_info",
                side_effect=lambda command, version, **_kwargs: DependencyBuildInfo(
                    version,
                    "dev_deflick" if "bracketlapse" in command[0] else "main",
                    "2026-08-08T12:30:00Z",
                    "abc123",
                ),
            ),
            patch(
                "timelapse_manager.dependency_manager.inspection.inspect_remote_branches",
                side_effect=lambda identifier: {
                    "camera": ("main", "dev"),
                    "bracketlapse": ("master", "dev_deflick"),
                    "sunsetscore": ("main", "opt/gpu-throughput"),
                }[identifier],
            ),
        ):
            progress = []
            statuses = DependencyInspector(Path.cwd()).inspect(
                {},
                lambda completed, total, name: progress.append(
                    (completed, total, name)
                ),
            )

        self.assertEqual(statuses[0].spec.identifier, "camera")
        self.assertEqual(statuses[1].spec.parent_id, "camera")
        self.assertEqual(statuses[7].state, "ready")
        self.assertEqual(statuses[8].spec.parent_id, "sunsetscore")
        self.assertEqual(statuses[9].state, "ready")
        self.assertEqual(statuses[2].build_info.branch, "dev_deflick")
        self.assertEqual(statuses[2].available_branches, ("master", "dev_deflick"))
        self.assertEqual(statuses[2].selected_branch, "master")
        self.assertEqual(statuses[7].build_info.build_time, "2026-08-08T12:30:00Z")
        self.assertEqual([item[0] for item in progress], list(range(1, 12)))
        self.assertTrue(all(item[1] == 11 for item in progress))

    def test_broken_native_command_is_reported_as_an_issue(self) -> None:
        inspector = DependencyInspector(Path.cwd())
        with (
            patch(
                "timelapse_manager.dependency_manager.inspection.resolve_command",
                return_value=["/private/enfuse"],
            ),
            patch(
                "timelapse_manager.dependency_manager.inspection.probe_command",
                return_value=CommandProbe(False, "健康检查退出码 9"),
            ),
        ):
            state, detail, _build = inspector._command("enfuse")

        self.assertEqual(state, "issue")
        self.assertIn("健康检查退出码 9", detail)


if __name__ == "__main__":
    unittest.main()
