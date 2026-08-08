from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.config import ConfigManager
from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.dependency_manager.runtime_dependencies import (
    resolve_runtime_commands,
)
from timelapse_manager.errors import ConfigError, ProcessError, TaskError
from timelapse_manager.maintenance import cleanup_work_directory
from timelapse_manager.paths import AppPaths
from timelapse_manager.presets import validate_task
from timelapse_manager.process_utils import resolve_command
from timelapse_manager.task_store import TaskStore
from tests.managed_dependency_support import install_fake_native_tools


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

    def test_private_command_takes_priority_over_ambient_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = DependencyPaths.discover(root)
            paths.ensure_layout()
            command = paths.bin_dir / "workflow-tool"
            command.touch(mode=0o755)
            with patch.dict(os.environ, {"PATH": "/global/bin"}, clear=False):
                resolved = resolve_command("workflow-tool", root=root)
            self.assertEqual(Path(resolved[0]).resolve(), command.resolve())

    @unittest.skipIf(os.name == "nt", "POSIX virtual-environment symlink test")
    def test_private_command_symlink_must_stay_inside_private_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = DependencyPaths.discover(root)
            paths.ensure_layout()
            target = paths.root / "tools" / "sunsetscore"
            target.parent.mkdir()
            target.touch(mode=0o755)
            (paths.bin_dir / "sunsetscore").symlink_to(target)

            resolved = resolve_command("sunsetscore", root=root)

            self.assertEqual(Path(resolved[0]).resolve(), target.resolve())

    def test_global_and_pipx_commands_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scripts = root / "global-bin"
            scripts.mkdir()
            command = scripts / "sunsetscore"
            command.touch(mode=0o755)
            environment = {"PATH": str(scripts), "PIPX_BIN_DIR": str(scripts)}

            with patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(ProcessError, "应用私有命令"):
                    resolve_command("sunsetscore", root=root)

    def test_runtime_environment_is_private_but_keeps_system_utilities(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = DependencyPaths.discover(Path(temp_dir))
            environment = paths.runtime_environment(
                {
                    "PATH": "/opt/homebrew/bin:/usr/local/bin:/ambient/bin",
                    "HOME": "/ambient/home",
                    "PIPX_HOME": "/ambient/pipx",
                    "PIPX_BIN_DIR": "/ambient/pipx/bin",
                    "HOMEBREW_PREFIX": "/opt/homebrew",
                    "UNCHANGED": "yes",
                }
            )

            path_entries = environment["PATH"].split(os.pathsep)
            self.assertEqual(
                path_entries[:4], [str(item) for item in paths.command_directories()]
            )
            self.assertNotIn("/opt/homebrew/bin", path_entries)
            self.assertNotIn("/usr/local/bin", path_entries)
            self.assertNotIn("PIPX_HOME", environment)
            self.assertEqual(environment["HOME"], str(paths.home_dir))
            self.assertEqual(environment["HOMEBREW_PREFIX"], str(paths.homebrew_dir))
            self.assertEqual(environment["UNCHANGED"], "yes")
            if os.name != "nt":
                self.assertIn("/usr/bin", path_entries)
                self.assertIn("/bin", path_entries)

            install_environment = paths.install_environment(environment)
            self.assertEqual(install_environment["UV_MANAGED_PYTHON"], "1")
            self.assertNotIn("UV_PYTHON_PREFERENCE", install_environment)
            with patch.dict(os.environ, {"AMBIENT_ONLY": "yes"}, clear=False):
                empty_base = paths.runtime_environment({})
            self.assertNotIn("AMBIENT_ONLY", empty_base)

    def test_broken_camera_wrapper_fails_preflight_health_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            install_fake_native_tools(root)
            command = f'{sys.executable} -c "import package_that_does_not_exist"'

            with self.assertRaisesRegex(ConfigError, "Camera.*不可用"):
                resolve_runtime_commands(
                    root,
                    {"camera": command},
                    processing_enabled=False,
                )

    def test_task_cannot_override_private_cache_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ConfigManager(AppPaths.discover(Path(temp_dir)))
            manager.ensure()
            task = TaskStore(manager.load()).create("环境隔离", "manual")
            task["environment"]["XDG_CACHE_HOME"] = "/ambient/cache"

            with self.assertRaisesRegex(ConfigError, "不能覆盖私有依赖环境"):
                validate_task(task)

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
