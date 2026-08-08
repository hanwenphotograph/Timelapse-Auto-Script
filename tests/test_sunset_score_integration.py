from __future__ import annotations

import time
import unittest

from timelapse_manager.io_utils import load_yaml, save_yaml, yaml_text
from tests.sunset_integration_support import SunsetScoreIntegrationTestCase


class SunsetScoreIntegrationTests(SunsetScoreIntegrationTestCase):
    def test_negative_score_deletes_hdr_after_video(self) -> None:
        state, work_dir, log = self._run_scheduled(
            {"FAKE_SUNSET_SCORES": "1"}, cleanup_enabled=False
        )

        self.assertEqual(state["status"], "completed", state)
        self.assertTrue((work_dir / "hdr_video" / "timelapse.mp4").exists())
        self.assertFalse((work_dir / "hdr_enfuse").exists())
        self.assertIn("晚霞评分已自动启用", log)
        self.assertLess(log.index("晚霞增量扫描完成"), log.index("Creating video"))
        self.assertLess(log.index("Creating video"), log.index("已删除 HDR 照片目录"))
        child_progress = {
            child["role"]: child.get("progress") for child in state["children"]
        }
        self.assertEqual(
            child_progress["bracketlapse-standby"],
            {"stage": "video", "completed": 2, "total": 2},
        )
        self.assertEqual(
            child_progress["sunsetscore-resident"],
            {"stage": "sunset", "completed": 2, "total": 2},
        )

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
        self.assertIn("SunsetScore 常驻服务启动失败，退出码=7", log)

    def test_partial_negative_score_fails_and_preserves_hdr(self) -> None:
        state, work_dir, log = self._run_scheduled(
            {
                "FAKE_CAMERA_ROUNDS": "3",
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

    def test_standby_scores_before_capture_finishes_and_reuses_model(
        self,
    ) -> None:
        events = self.root / "model-events.txt"
        state, _work_dir, log = self._run_scheduled(
            {
                "FAKE_CAMERA_ROUNDS": "5",
                "FAKE_CAMERA_DELAY": "0.08",
                "FAKE_SUNSET_SCORES": "4",
                "FAKE_SUNSET_MODEL_EVENTS": str(events),
            },
            cleanup_enabled=False,
        )

        self.assertEqual(state["status"], "completed", state)
        self.assertLess(
            log.index("[bracketlapse-standby] Fusing"),
            log.index("Scheduled end time"),
        )
        self.assertLess(log.index("晚霞增量扫描完成"), log.index("Creating video"))
        event_lines = events.read_text(encoding="utf-8").splitlines()
        self.assertEqual(event_lines.count("model-start"), 1)
        self.assertGreaterEqual(
            sum(line.startswith("score:") for line in event_lines), 1
        )

    def test_eternal_batches_share_one_score_model(self) -> None:
        events = self.root / "eternal-model-events.txt"
        task = self.service.create_task("永续模型复用", "eternal")
        definition = self.service.store.load(task["id"])
        definition["environment"] = {
            "FAKE_CAMERA_ROUNDS": "10",
            "FAKE_CAMERA_DELAY": "0.03",
            "FAKE_SUNSET_SCORES": "4",
            "FAKE_SUNSET_MODEL_EVENTS": str(events),
        }
        definition["eternal"]["batch_groups"] = 2
        self.service.store.save_text(task["id"], yaml_text(definition))
        self.service.start_task(task["id"])
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            state = self.service.store.read_state(task["id"], reconcile=True)
            if state.get("progress", {}).get("eternal_batches", 0) >= 3:
                break
            time.sleep(0.05)
        self.service.request(task["id"], "finish_now")

        state = self._wait_terminal(task["id"], timeout=25)

        self.assertEqual(state["status"], "completed", state)
        event_lines = events.read_text(encoding="utf-8").splitlines()
        self.assertEqual(event_lines.count("model-start"), 1)
        self.assertGreaterEqual(
            sum(line.startswith("score:") for line in event_lines), 2
        )


if __name__ == "__main__":
    unittest.main()
