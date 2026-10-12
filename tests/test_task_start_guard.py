from __future__ import annotations

import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from timelapse_manager.errors import TaskError
from timelapse_manager.io_utils import yaml_text
from timelapse_manager.process_utils import process_identity
from timelapse_manager.service import ManagerService


class TaskStartGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = ManagerService(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_different_chains_cannot_capture_same_work_directory(self) -> None:
        first = self.service.create_task("first", "scheduled_loop")
        second = self.service.create_task("second", "scheduled_loop")
        self.service._claim_start(first)
        with self.assertRaisesRegex(TaskError, "工作目录已有活动任务"):
            self.service._claim_start(second)

    def test_overlapping_capture_in_different_directories_is_rejected(self) -> None:
        first = self.service.create_task("first", "scheduled_once")
        second = self.service.create_task("second", "scheduled_once")
        second["capture"]["work_dir"] = str(self.root / "different")
        self.service.store.save_text(second["id"], yaml_text(second))
        self.service._claim_start(first)
        with self.assertRaisesRegex(TaskError, "相机不能被重复占用"):
            self.service._claim_start(second)

    def test_nonoverlapping_schedules_can_be_claimed(self) -> None:
        first = self.service.create_task("first", "scheduled_once")
        second = self.service.create_task("second", "scheduled_once")
        future = datetime.now() + timedelta(days=2)
        second["capture"].update(
            {
                "work_dir": str(self.root / "future"),
                "start_date": future.date().isoformat(),
                "start_at": "15:00",
                "end_date": future.date().isoformat(),
                "end_at": "21:00",
            }
        )
        self.service.store.save_text(second["id"], yaml_text(second))
        self.service._claim_start(first)
        self.assertEqual(self.service._claim_start(second)["status"], "starting")

    def test_failed_worker_with_live_children_cannot_restart(self) -> None:
        task = self.service.create_task("orphan", "scheduled_once")
        state = self.service.store.default_state(task["id"])
        state.update(
            {
                "status": "failed",
                "children": [
                    {
                        "role": "camera-timelapse",
                        "pid": os.getpid(),
                        "created_at": process_identity(os.getpid()),
                    }
                ],
            }
        )
        self.service.store.write_state(task["id"], state)
        with self.assertRaisesRegex(TaskError, "残留进程"):
            self.service._claim_start(task)

    def test_concurrent_start_only_claims_one_conflicting_task(self) -> None:
        tasks = [self.service.create_task(str(i), "scheduled_loop") for i in range(2)]

        def claim(task):
            try:
                self.service._claim_start(task)
                return True
            except TaskError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, tasks))
        self.assertEqual(sum(results), 1)


if __name__ == "__main__":
    unittest.main()
