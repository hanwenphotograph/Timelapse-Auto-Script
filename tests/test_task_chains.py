from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from timelapse_manager.config import ConfigManager
from timelapse_manager.errors import TaskError
from timelapse_manager.io_utils import load_yaml, save_yaml, yaml_text
from timelapse_manager.paths import AppPaths
from timelapse_manager.task_chain import TaskChainManager
from timelapse_manager.task_factory import (
    create_successor_definition,
    create_task_definition,
)
from timelapse_manager.task_store import TaskStore


class TaskChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = ConfigManager(AppPaths.discover(self.root))
        self.manager.ensure()
        project = load_yaml(self.manager.paths.config_file)
        project["auto_root"] = str(self.root / "output")
        save_yaml(self.manager.paths.config_file, project)
        self.store = TaskStore(self.manager.load())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_scheduled_presets_materialize_complete_manual_yaml(self) -> None:
        now = datetime(2026, 7, 21, 12, 0)
        once = create_task_definition(
            self.store.config, "scheduled-once", "今日任务", "scheduled_once", now=now
        )
        loop = create_task_definition(
            self.store.config, "scheduled-loop", "日常任务", "scheduled_loop", now=now
        )
        for task in (once, loop):
            self.assertEqual(task["schema_version"], 2)
            self.assertEqual(task["preset"], "manual")
            self.assertNotIn("null", yaml_text(task))
            self.assertNotIn("eternal", task)
            self.assertEqual(task["capture"]["start_date"], "2026-07-21")
            self.assertEqual(task["capture"]["start_at"], "16:00")
            self.assertEqual(task["capture"]["interval_seconds"], 6)
        self.assertNotIn("continuation", once)
        self.assertEqual(loop["continuation"]["sequence"], 1)
        self.assertIn("黄昏 2026-07-21", loop["name"])

    def test_successor_uses_latest_project_configuration(self) -> None:
        first = create_task_definition(
            self.store.config,
            "scheduled-loop",
            "日常任务",
            "scheduled_loop",
            now=datetime(2026, 7, 21, 12, 0),
        )
        project = load_yaml(self.manager.paths.config_file)
        project["capture_interval_seconds"] = 11
        project["dusk"]["start_at"] = "17:00"
        save_yaml(self.manager.paths.config_file, project)
        latest = self.manager.load()
        successor = create_successor_definition(
            latest,
            "scheduled-loop-next",
            first,
            now=datetime(2026, 7, 21, 13, 0),
        )
        self.assertEqual(successor["capture"]["interval_seconds"], 11)
        self.assertEqual(successor["capture"]["start_at"], "17:00")
        self.assertEqual(successor["continuation"]["sequence"], 2)
        self.assertEqual(
            successor["continuation"]["previous_task_id"], first["id"]
        )

    def test_legacy_scheduled_task_migrates_once_when_inactive(self) -> None:
        task_id = "legacy-loop"
        legacy = self._legacy_task(task_id)
        save_yaml(self.store.definition_path(task_id), legacy)
        migrated = self.store.load(task_id)
        first_text = self.store.read_text(task_id)
        self.assertEqual(migrated["preset"], "manual")
        self.assertEqual(migrated["schema_version"], 2)
        self.assertNotIn("null", first_text)
        self.assertNotIn("eternal", load_yaml(self.store.definition_path(task_id)))
        self.assertEqual(self.store.read_text(task_id), first_text)

    def test_active_legacy_task_defers_migration(self) -> None:
        task_id = "legacy-active"
        legacy = self._legacy_task(task_id)
        save_yaml(self.store.definition_path(task_id), legacy)
        state = self.store.default_state(task_id)
        state.update({"status": "starting", "runner_pid": None})
        self.store.write_state(task_id, state)
        self.assertEqual(self.store.load(task_id)["preset"], "scheduled_loop")
        state.update({"status": "completed", "ended_at": datetime.now().isoformat()})
        self.store.write_state(task_id, state)
        self.assertEqual(self.store.load(task_id)["preset"], "manual")

    def test_successor_is_idempotent_and_history_cannot_restart(self) -> None:
        first = self.store.create("日常任务", "scheduled_loop")
        chains = TaskChainManager(self.store)
        second = chains.create_successor(first)
        duplicate = chains.create_successor(first)
        self.assertEqual(second["id"], duplicate["id"])
        with self.assertRaisesRegex(TaskError, "已有后继"):
            chains.validate_start(first)

    def test_chain_rejects_a_second_active_task(self) -> None:
        first = self.store.create("日常任务", "scheduled_loop")
        chains = TaskChainManager(self.store)
        second = chains.create_successor(first)
        state = self.store.default_state(first["id"])
        state.update({"status": "starting", "runner_pid": None})
        self.store.write_state(first["id"], state)
        with self.assertRaisesRegex(TaskError, "已有活动任务"):
            chains.validate_start(second)

    def test_chain_identity_cannot_be_changed(self) -> None:
        task = self.store.create("日常任务", "scheduled_loop")
        changed = self.store.load(task["id"])
        changed["continuation"]["chain_id"] = "different-chain"
        with self.assertRaisesRegex(TaskError, "链身份字段不能修改"):
            self.store.save_text(task["id"], yaml_text(changed))

    def test_retention_only_removes_expired_completed_chain_tasks(self) -> None:
        first = self.store.create("日常任务", "scheduled_loop")
        chains = TaskChainManager(self.store)
        second = chains.create_successor(first)
        now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
        old = (now - timedelta(days=31)).isoformat()
        first_state = self.store.default_state(first["id"])
        first_state.update({"status": "completed", "ended_at": old})
        self.store.write_state(first["id"], first_state)
        second_state = self.store.default_state(second["id"])
        second_state.update({"status": "failed", "ended_at": old})
        self.store.write_state(second["id"], second_state)
        output = self.store.config.auto_root / "keep" / "timelapse.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"video")
        removed = chains.prune_completed(first["continuation"]["chain_id"], now=now)
        self.assertEqual(removed, [first["id"]])
        self.assertFalse(self.store.definition_path(first["id"]).exists())
        self.assertTrue(self.store.definition_path(second["id"]).exists())
        self.assertTrue(output.exists())

    @staticmethod
    def _legacy_task(task_id: str) -> dict:
        return {
            "schema_version": 1,
            "id": task_id,
            "name": "旧循环",
            "preset": "scheduled_loop",
            "created_at": "2026-07-01T00:00:00+08:00",
            "capture": {
                "work_dir": None,
                "start_date": None,
                "start_at": None,
                "end_date": None,
                "end_at": None,
                "interval_seconds": None,
            },
            "processing": {"enabled": True},
            "cleanup": {
                "enabled": True,
                "keep_directories": ["hdr_enfuse", "hdr_video"],
                "delete_incomplete_groups": True,
                "on_failure": True,
            },
            "retry": {"enabled": True, "delay_seconds": None},
            "eternal": {
                "batch_groups": None,
                "images_per_group": None,
                "state_dir": None,
            },
            "environment": {},
        }


if __name__ == "__main__":
    unittest.main()
