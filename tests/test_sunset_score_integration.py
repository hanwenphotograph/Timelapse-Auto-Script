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
FAKE_SUNSET = REPOSITORY / "tests" / "fixtures" / "fake_sunsetscore.py"


def command_for(script: Path) -> str:
    return f'"{sys.executable}" "{script}"'


class SunsetScoreIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = AppPaths.discover(self.root)
        manager = ConfigManager(self.paths)
        manager.ensure()
        project = load_yaml(self.paths.config_file)
        project["auto_root"] = str(self.root / "output")
        project["commands"].update(
            {
                "camera": command_for(FAKE_CAMERA),
                "bracketlapse": command_for(FAKE_BRACKET),
                "bracketlapse_fallback": "",
                "sunsetscore": command_for(FAKE_SUNSET),
            }
        )
        project["sunset_score"]["interval"] = 1
        project["runtime"]["startup_probe_seconds"] = 0.05
        project["eternal"]["batch_groups"] = 2
        save_yaml(self.paths.config_file, project)
        self.service = ManagerService(self.root)

    def tearDown(self) -> None:
        for item in self.service.list_tasks():
            if item["state"]["status"] in ACTIVE_STATUSES:
                try:
                    self.service.request(item["task"]["id"], "stop")
                except Exception:
                    pass
        time.sleep(0.2)
        self.temp.cleanup()

    def _run_scheduled(
        self,
        environment: dict[str, str],
        *,
        keep_directories: list[str] | None = None,
        cleanup_enabled: bool | None = None,
    ) -> tuple[dict, Path, str]:
        task = self.service.create_task("晚霞评分集成测试", "scheduled_once")
        definition = self.service.store.load(task["id"])
        definition["environment"] = environment
        if keep_directories is not None:
            definition["cleanup"]["keep_directories"] = keep_directories
        if cleanup_enabled is not None:
            definition["cleanup"]["enabled"] = cleanup_enabled
        self.service.store.save_text(task["id"], yaml_text(definition))
        self.service.start_task(task["id"])
        state = self._wait_terminal(task["id"])
        work_dir = Path(definition["capture"]["work_dir"])
        log = self.service.store.log_path(task["id"]).read_text(encoding="utf-8")
        return state, work_dir, log

    def _wait_terminal(self, task_id: str, timeout: float = 15) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.service.store.read_state(task_id, reconcile=True)
            if state["status"] not in ACTIVE_STATUSES:
                return state
            time.sleep(0.05)
        self.fail(f"任务 {task_id} 未在 {timeout} 秒内结束")

    def test_negative_score_deletes_hdr_after_video(self) -> None:
        state, work_dir, log = self._run_scheduled(
            {"FAKE_SUNSET_SCORES": "1"}, cleanup_enabled=False
        )

        self.assertEqual(state["status"], "completed", state)
        self.assertTrue((work_dir / "hdr_video" / "timelapse.mp4").exists())
        self.assertFalse((work_dir / "hdr_enfuse").exists())
        self.assertIn("晚霞评分已自动启用", log)
        self.assertLess(log.index("Creating video"), log.index("晚霞评分:"))

    def test_positive_score_overrides_cleanup_keep_list(self) -> None:
        state, work_dir, _log = self._run_scheduled(
            {"FAKE_SUNSET_SCORES": "4"},
            keep_directories=["hdr_video"],
        )

        self.assertEqual(state["status"], "completed", state)
        self.assertTrue((work_dir / "hdr_enfuse" / "frame-0001.jpg").exists())
        self.assertTrue((work_dir / "hdr_video" / "timelapse.mp4").exists())

    def test_scoring_failure_fails_task_and_preserves_hdr(self) -> None:
        state, work_dir, log = self._run_scheduled(
            {"FAKE_SUNSET_EXIT_CODE": "7"},
            keep_directories=["hdr_video"],
        )

        self.assertEqual(state["status"], "failed", state)
        self.assertTrue((work_dir / "hdr_enfuse" / "frame-0001.jpg").exists())
        self.assertIn("SunsetScore 退出码为 7", log)

    def test_partial_negative_score_fails_and_preserves_hdr(self) -> None:
        state, work_dir, log = self._run_scheduled(
            {
                "FAKE_BRACKET_FRAMES": "3",
                "FAKE_SUNSET_SCORES": "1,1,1",
                "FAKE_SUNSET_FAILED_INDEXES": "2",
            }
        )

        self.assertEqual(state["status"], "failed", state)
        self.assertTrue((work_dir / "hdr_enfuse" / "frame-0001.jpg").exists())
        self.assertIn("结果不足以安全删图", log)

    def test_unavailable_scorer_preserves_legacy_flow(self) -> None:
        project = load_yaml(self.paths.config_file)
        project["commands"]["sunsetscore"] = "missing-sunsetscore-for-test"
        save_yaml(self.paths.config_file, project)
        self.service.reload()

        state, work_dir, log = self._run_scheduled({})

        self.assertEqual(state["status"], "completed", state)
        self.assertTrue((work_dir / "hdr_enfuse").is_dir())
        self.assertIn("晚霞评分未启用", log)
        self.assertNotIn("晚霞评分结果", log)

    def test_eternal_batch_uses_sunset_retention(self) -> None:
        task = self.service.create_task("永续晚霞评分", "eternal")
        definition = self.service.store.load(task["id"])
        definition["environment"] = {
            "FAKE_CAMERA_ROUNDS": "6",
            "FAKE_CAMERA_DELAY": "0.02",
            "FAKE_SUNSET_SCORES": "4",
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

        state = self._wait_terminal(task["id"], timeout=20)

        self.assertEqual(state["status"], "completed", state)
        self.assertTrue(list((self.root / "output").rglob("hdr_enfuse/frame-0001.jpg")))


if __name__ == "__main__":
    unittest.main()
