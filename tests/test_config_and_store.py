from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.config import ConfigManager
from timelapse_manager.errors import ConfigError
from timelapse_manager.paths import AppPaths
from timelapse_manager.presets import PRESET_DESCRIPTIONS
from timelapse_manager.task_store import TaskStore


class ConfigAndStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = ConfigManager(AppPaths.discover(self.root))
        self.manager.ensure()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_defaults_are_valid_and_cross_platform(self) -> None:
        loaded = self.manager.load()
        self.assertEqual(loaded.project["schema_version"], 1)
        self.assertTrue(loaded.auto_root.is_absolute())
        self.assertEqual(loaded.webhook["enabled"], False)

    def test_project_yaml_roundtrip(self) -> None:
        text = self.manager.read_text("project").replace(
            "capture_interval_seconds: 6", "capture_interval_seconds: 8"
        )
        self.manager.save_text("project", text)
        self.assertEqual(self.manager.load().project["capture_interval_seconds"], 8)

    def test_invalid_schedule_is_rejected(self) -> None:
        text = self.manager.read_text("project").replace(
            "start_at: '16:00'", "start_at: '08:00'"
        )
        with self.assertRaises(ConfigError):
            self.manager.save_text("project", text)

    def test_presets_create_expected_execution_modes(self) -> None:
        store = TaskStore(self.manager.load())
        expected = {
            "scheduled_once": "manual",
            "scheduled_loop": "manual",
            "manual": "manual",
            "eternal": "eternal",
        }
        for preset in PRESET_DESCRIPTIONS:
            task = store.create(preset, preset)
            self.assertEqual(store.load(task["id"])["preset"], expected[preset])
            if preset.startswith("scheduled_"):
                self.assertNotIn("null", store.read_text(task["id"]))
        self.assertEqual(len(store.list_definitions()), len(PRESET_DESCRIPTIONS))

    def test_reconcile_does_not_overwrite_newer_terminal_state(self) -> None:
        store = TaskStore(self.manager.load())
        task = store.create("竞态回归测试", "scheduled_once")
        active = store.default_state(task["id"])
        active.update(
            {
                "status": "running",
                "runner_pid": 12345,
                "runner_created_at": 67890.0,
            }
        )
        store.write_state(task["id"], active)

        def finish_while_reconciling(*_args: object) -> bool:
            terminal = store.read_state(task["id"])
            terminal.update(
                {
                    "status": "completed",
                    "phase": "任务已完成",
                    "runner_pid": None,
                    "runner_created_at": None,
                }
            )
            store.write_state(task["id"], terminal)
            return False

        with patch(
            "timelapse_manager.task_store.process_matches",
            side_effect=finish_while_reconciling,
        ):
            reconciled = store.read_state(task["id"], reconcile=True)

        self.assertEqual(reconciled["status"], "completed")
        self.assertEqual(store.read_state(task["id"])["status"], "completed")


if __name__ == "__main__":
    unittest.main()
