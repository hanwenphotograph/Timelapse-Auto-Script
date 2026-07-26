from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.cli import _foreground_start
from timelapse_manager.config import ConfigManager
from timelapse_manager.io_utils import load_yaml, save_yaml
from timelapse_manager.paths import AppPaths
from timelapse_manager.service import ManagerService
from timelapse_manager.task_store import ACTIVE_STATUSES


REPOSITORY = Path(__file__).resolve().parents[1]
FAKE_CAMERA = REPOSITORY / "tests" / "fixtures" / "fake_camera.py"
FAKE_BRACKET = REPOSITORY / "tests" / "fixtures" / "fake_bracketlapse.py"


def command_for(script: Path) -> str:
    return f'"{sys.executable}" "{script}"'


class TaskContinuationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        paths = AppPaths.discover(self.root)
        manager = ConfigManager(paths)
        manager.ensure()
        project = load_yaml(paths.config_file)
        project["auto_root"] = str(self.root / "output")
        project["commands"]["camera"] = command_for(FAKE_CAMERA)
        project["commands"]["bracketlapse"] = command_for(FAKE_BRACKET)
        project["commands"]["bracketlapse_fallback"] = ""
        project["runtime"]["startup_probe_seconds"] = 0.05
        project["runtime"]["retry_delay_seconds"] = 0.1
        save_yaml(paths.config_file, project)
        self.paths = paths
        self.service = ManagerService(self.root)

    def tearDown(self) -> None:
        for item in self.service.list_tasks():
            if item["state"]["status"] in ACTIVE_STATUSES:
                try:
                    self.service.request(item["task"]["id"], "stop")
                except Exception:
                    pass
        time.sleep(0.3)
        self.temp.cleanup()

    def test_successful_round_starts_one_successor(self) -> None:
        environment = {"FAKE_CAMERA_ROUNDS": "30", "FAKE_CAMERA_DELAY": "0.03"}
        with patch.dict(os.environ, environment, clear=False):
            first = self.service.create_task("日常任务", "scheduled_loop")
            self.service.start_task(first["id"])
            second = self._wait_for_successor(first["id"])
            self.service.request(second["id"], "finish_after_current")
            second_state = self._wait_terminal(second["id"])

        self.assertEqual(second_state["status"], "completed", second_state)
        time.sleep(0.3)
        tasks = self._chain_tasks(first["continuation"]["chain_id"])
        self.assertEqual(len(tasks), 2)
        first_state = self.service.store.read_state(first["id"], reconcile=True)
        self.assertEqual(first_state["status"], "completed")
        self.assertEqual(second["continuation"]["previous_task_id"], first["id"])

    def test_failed_round_retries_as_new_task(self) -> None:
        project = load_yaml(self.paths.config_file)
        project["runtime"]["retry_delay_seconds"] = 1
        save_yaml(self.paths.config_file, project)
        self.service.reload()
        environment = {
            "FAKE_CAMERA_ROUNDS": "2",
            "FAKE_CAMERA_DELAY": "0.03",
            "FAKE_CAMERA_EXIT_CODE": "7",
        }
        with patch.dict(os.environ, environment, clear=False):
            first = self.service.create_task("失败重试", "scheduled_loop")
            self.service.start_task(first["id"])
            second = self._wait_for_successor(first["id"], timeout=5)
            self.service.request(second["id"], "finish_after_current")
            second_state = self._wait_terminal(second["id"])

        self.assertEqual(second_state["status"], "failed", second_state)
        first_state = self.service.store.read_state(first["id"], reconcile=True)
        self.assertEqual(first_state["status"], "failed")
        time.sleep(0.3)
        tasks = self._chain_tasks(first["continuation"]["chain_id"])
        self.assertEqual(len(tasks), 2)

    def test_foreground_round_hands_off_to_background(self) -> None:
        environment = {"FAKE_CAMERA_ROUNDS": "30", "FAKE_CAMERA_DELAY": "0.02"}
        with patch.dict(os.environ, environment, clear=False):
            first = self.service.create_task("前台接力", "scheduled_loop")
            with redirect_stderr(StringIO()):
                self.assertEqual(_foreground_start(self.service, first["id"]), 0)
            second = self._wait_for_successor(first["id"])
            second_state = self.service.store.read_state(second["id"], reconcile=True)
            self.assertIsInstance(second_state.get("runner_pid"), int)
            self.service.request(second["id"], "finish_after_current")
            self._wait_terminal(second["id"])

        time.sleep(0.3)
        tasks = self._chain_tasks(first["continuation"]["chain_id"])
        self.assertEqual(len(tasks), 2)

    def _wait_for_successor(self, first_id: str, timeout: float = 8) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for item in self.service.list_tasks():
                task = item["task"]
                if (
                    task.get("continuation", {}).get("previous_task_id") == first_id
                    and item["state"]["status"] in ACTIVE_STATUSES
                ):
                    return task
            time.sleep(0.05)
        self.fail("未等到活动的后继任务")

    def _wait_terminal(self, task_id: str, timeout: float = 8) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.service.store.read_state(task_id, reconcile=True)
            if state["status"] not in ACTIVE_STATUSES:
                return state
            time.sleep(0.05)
        self.fail(f"任务 {task_id} 未进入终态")

    def _chain_tasks(self, chain_id: str) -> list[dict]:
        return [
            item["task"]
            for item in self.service.list_tasks()
            if item["task"].get("continuation", {}).get("chain_id") == chain_id
        ]


if __name__ == "__main__":
    unittest.main()
