from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

from timelapse_manager.config import ConfigManager
from timelapse_manager.io_utils import load_yaml, save_yaml, yaml_text
from timelapse_manager.paths import AppPaths
from timelapse_manager.service import ManagerService
from timelapse_manager.task_store import ACTIVE_STATUSES


REPOSITORY = Path(__file__).resolve().parents[1]
FAKE_CAMERA = REPOSITORY / "tests" / "fixtures" / "fake_camera.py"
FAKE_BRACKET = REPOSITORY / "tests" / "fixtures" / "fake_bracketlapse.py"


def command_for(script: Path) -> str:
    return f'"{sys.executable}" "{script}"'


class IntegrationTests(unittest.TestCase):
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
        project["eternal"]["batch_groups"] = 2
        save_yaml(paths.config_file, project)
        self.service = ManagerService(self.root)

    def tearDown(self) -> None:
        for item in self.service.list_tasks():
            state = item["state"]
            if state["status"] in ACTIVE_STATUSES:
                try:
                    self.service.request(item["task"]["id"], "stop")
                except Exception:
                    pass
        time.sleep(0.2)
        self.temp.cleanup()

    def wait_terminal(self, task_id: str, timeout: float = 12) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.service.store.read_state(task_id, reconcile=True)
            if state["status"] not in ACTIVE_STATUSES:
                return state
            time.sleep(0.05)
        self.fail(f"任务 {task_id} 未在 {timeout} 秒内结束")

    def test_detached_scheduled_task_runs_and_cleans_output(self) -> None:
        task = self.service.create_task("集成测试单次任务", "scheduled_once")
        started = self.service.start_task(task["id"])
        self.assertIsInstance(started.get("runner_pid"), int)
        state = self.wait_terminal(task["id"])
        self.assertEqual(state["status"], "completed", state)
        output_root = self.root / "output"
        videos = list(output_root.rglob("timelapse.mp4"))
        raw_images = list(output_root.rglob("0001_0.jpg"))
        self.assertTrue(videos)
        self.assertFalse(raw_images)

    def test_eternal_task_can_finish_now_and_drain_batches(self) -> None:
        task = self.service.create_task("集成测试永续任务", "eternal")
        definition = self.service.store.load(task["id"])
        definition["environment"] = {
            "FAKE_CAMERA_ROUNDS": "30",
            "FAKE_CAMERA_DELAY": "0.03",
        }
        definition["eternal"]["batch_groups"] = 2
        self.service.store.save_text(task["id"], yaml_text(definition))
        self.service.start_task(task["id"])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.service.store.read_state(task["id"], reconcile=True)
            if state.get("progress", {}).get("eternal_batches", 0) >= 1:
                break
            time.sleep(0.05)
        self.service.request(task["id"], "finish_now")
        state = self.wait_terminal(task["id"], timeout=15)
        self.assertEqual(state["status"], "completed", state)
        self.assertTrue(list((self.root / "output").rglob("timelapse.mp4")))
        self.assertFalse(
            list((self.root / "output" / ".eternal" / "queue").glob("*.ready.yaml"))
        )


if __name__ == "__main__":
    unittest.main()
