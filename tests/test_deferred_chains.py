from __future__ import annotations

import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from timelapse_manager.io_utils import yaml_text
from timelapse_manager.task_store import ACTIVE_STATUSES
from tests import test_deferred_processing as support


class DeferredChainTests(unittest.TestCase):
    setUp = support.DeferredProcessingIntegrationTests.setUp
    tearDown = support.DeferredProcessingIntegrationTests.tearDown
    wait_terminal = support.DeferredProcessingIntegrationTests.wait_terminal
    configure_deferred = support.DeferredProcessingIntegrationTests.configure_deferred

    def test_recurring_capture_continues_while_processing_waits(self):
        self.configure_deferred()
        first = self.service.create_task("定时后期接力", "scheduled_loop")
        # The fake camera completes immediately; model a slot that really ended
        # before now so continuation selects a different capture directory.
        previous_date = (datetime.now() - timedelta(days=1)).date().isoformat()
        first["capture"].update(start_date=previous_date, end_date=previous_date)
        old_dir = Path(first["capture"]["work_dir"])
        first["capture"]["work_dir"] = str(old_dir.parent.parent / previous_date / old_dir.name)
        first["environment"] = {"FAKE_CAMERA_ROUNDS": "20", "FAKE_CAMERA_DELAY": "0.04"}
        self.service.store.save_text(first["id"], yaml_text(first))
        self.service.start_task(first["id"])
        second = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            for task in self.service.store.list_definitions():
                if task.get("continuation", {}).get("previous_task_id") == first["id"]:
                    state = self.service.store.read_state(task["id"], reconcile=True)
                    if state["status"] in ACTIVE_STATUSES:
                        second = task
                        break
            if second:
                break
            time.sleep(0.02)
        self.assertIsNotNone(second, "待处理照片不应阻塞下一个拍摄任务")
        self.service.request(second["id"], "finish_after_current")
        self.assertEqual(self.wait_terminal(second["id"])["status"], "completed")
        first_state = self.service.store.read_state(first["id"])
        queued_id = first_state["progress"]["processing_task_id"]
        self.assertEqual(self.service.store.read_state(queued_id)["status"], "idle")
        self.assertEqual(first_state["status"], "completed")
