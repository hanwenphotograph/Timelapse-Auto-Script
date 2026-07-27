from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.dependency_manager.inspection import DependencyInspector
from timelapse_manager.dependency_manager.installation import (
    PACKAGE_URLS,
    DependencyInstaller,
    _console_script_python,
)
from timelapse_manager.dependency_manager.sunset_resources import (
    MODEL_NAME,
    MODEL_SIZE,
    PROJECTOR_NAME,
    PROJECTOR_SIZE,
    inspect_sunset_resources,
)
from timelapse_manager.sunset_score.availability import SunsetScoreAvailability


class SunsetResourceTests(unittest.TestCase):
    def test_complete_runtime_and_models_are_reported_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            models = home / "models"
            models.mkdir()
            with (models / MODEL_NAME).open("wb") as handle:
                handle.truncate(MODEL_SIZE)
            with (models / PROJECTOR_NAME).open("wb") as handle:
                handle.truncate(PROJECTOR_SIZE)

            runtime = home / "runtime" / "b10040-test" / "bin"
            runtime.mkdir(parents=True)
            executable = runtime / "llama-mtmd-cli"
            executable.touch()
            executable.with_name("llama-server").touch()
            marker = runtime.parent / ".installed.json"
            marker.write_text(
                json.dumps(
                    {
                        "release": "b10040",
                        "backend": "cpu",
                        "executable": "bin/llama-mtmd-cli",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"SUNSETSCORE_HOME": temp_dir}):
                results = inspect_sunset_resources()

        self.assertEqual({state for state, _detail in results.values()}, {"ready"})
        self.assertIn("CPU", results["sunset_runtime"][1])

    def test_incomplete_model_is_not_reported_as_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            models = Path(temp_dir) / "models"
            models.mkdir()
            (models / MODEL_NAME).write_bytes(b"partial")
            with patch.dict(os.environ, {"SUNSETSCORE_HOME": temp_dir}):
                state, detail = inspect_sunset_resources()["sunset_model"]

        self.assertEqual(state, "issue")
        self.assertIn("文件不完整", detail)


class DependencyInspectionTests(unittest.TestCase):
    def test_parent_and_child_dependencies_keep_catalog_order(self) -> None:
        sunset = SunsetScoreAvailability(("/tools/sunsetscore",), "0.9.0")
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
                "timelapse_manager.dependency_manager.inspection.inspect_sunset_resources",
                return_value=resources,
            ),
        ):
            statuses = DependencyInspector().inspect({})

        self.assertEqual(statuses[0].spec.identifier, "camera")
        self.assertEqual(statuses[1].spec.parent_id, "camera")
        self.assertEqual(statuses[6].state, "ready")
        self.assertEqual(statuses[7].spec.parent_id, "sunsetscore")
        self.assertEqual(statuses[8].state, "ready")


class DependencyInstallationTests(unittest.TestCase):
    def test_source_install_uses_the_active_python_environment(self) -> None:
        installer = DependencyInstaller(Path.cwd())
        with patch.object(sys, "frozen", False, create=True):
            plan = installer.plan("python:sunsetscore", {})

        assert plan is not None
        self.assertEqual(plan.command[:4], (sys.executable, "-m", "pip", "install"))
        self.assertEqual(plan.command[-1], PACKAGE_URLS["sunsetscore"])

    @unittest.skipIf(os.name == "nt", "POSIX console-script shebang test")
    def test_sunset_prepare_uses_console_scripts_exact_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            exact_python = directory / "python3.10"
            neighboring_python = directory / "python"
            script = directory / "sunsetscore"
            exact_python.touch()
            neighboring_python.touch()
            script.write_text(f"#!{exact_python}\n", encoding="utf-8")

            result = _console_script_python(script)

        self.assertEqual(result, exact_python)


if __name__ == "__main__":
    unittest.main()
