from __future__ import annotations

import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from timelapse_manager.io_utils import (
    load_json,
    load_yaml,
    now_iso,
    save_yaml,
)
from timelapse_manager.process_utils import terminate_tree
from timelapse_manager.processing.scheduler import dispatch_once
from timelapse_manager.service import ManagerService
from timelapse_manager.workflows.eternal import EternalWorkflow
from tests import test_integration as support


class DeferredProcessingIntegrationTests(unittest.TestCase):
    setUp = support.IntegrationTests.setUp
    wait_terminal = support.IntegrationTests.wait_terminal

    def tearDown(self):
        owner = load_json(
            self.service.store.runtime_dir / "processing-scheduler.json", {}
        )
        if owner.get("pid"):
            terminate_tree(owner["pid"], 2)
        support.IntegrationTests.tearDown(self)

    def configure_deferred(self):
        project = load_yaml(self.service.paths.config_file)
        future = datetime.now() + timedelta(minutes=10)
        project["photo_processing"] = {
            "mode": "scheduled",
            "start_at": future.strftime("%H:%M"),
        }
        save_yaml(self.service.paths.config_file, project)
        self.service.reload()

    def capture(self):
        self.configure_deferred()
        task = self.service.create_task("定时处理", "scheduled_once")
        self.service.start_task(task["id"])
        state = self.wait_terminal(task["id"])
        self.assertEqual(state["status"], "completed", state)
        processing_id = state["progress"]["processing_task_id"]
        return task, processing_id

    def release_and_wait(self, processing_id):
        project = load_yaml(self.service.paths.config_file)
        project["photo_processing"]["mode"] = "immediate"
        save_yaml(self.service.paths.config_file, project)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = self.service.store.read_state(processing_id, reconcile=True)
            if state["status"] in {"completed", "failed"}:
                return state
            time.sleep(0.05)
        self.fail("后期处理任务未在超时前结束")

    def test_capture_only_downloads_then_detached_scheduler_processes(self):
        task, processing_id = self.capture()
        work_dir = Path(task["capture"]["work_dir"])
        self.assertTrue((work_dir / "0001_01.jpg").is_file())
        self.assertFalse(list(work_dir.rglob("timelapse.mp4")))
        state = self.service.store.read_state(task["id"])
        self.assertEqual(
            [child["role"] for child in state["children"]], ["camera-timelapse"]
        )
        self.assertEqual(self.service.store.read_state(processing_id)["status"], "idle")
        # Post-processing must not depend on the camera still being installed/connected.
        project = load_yaml(self.service.paths.config_file)
        project["commands"]["camera"] = "missing-camera-for-processing-test"
        save_yaml(self.service.paths.config_file, project)
        state = self.release_and_wait(processing_id)
        self.assertEqual(state["status"], "completed", state)
        self.assertTrue(list(work_dir.rglob("timelapse.mp4")))
        self.assertFalse((work_dir / "0001_01.jpg").exists())
        self.assertFalse(any("camera" in child["role"] for child in state["children"]))

    def test_missing_processing_dependency_keeps_downloaded_material(self):
        self.configure_deferred()
        project = load_yaml(self.service.paths.config_file)
        project["commands"]["bracketlapse"] = "missing-bracket-for-test"
        save_yaml(self.service.paths.config_file, project)
        task, processing_id = self.capture()
        state = self.release_and_wait(processing_id)
        self.assertEqual(state["status"], "failed", state)
        self.assertTrue((Path(task["capture"]["work_dir"]) / "0001_01.jpg").is_file())

    def test_queue_is_restored_when_manager_reopens(self):
        _, processing_id = self.capture()
        owner = load_json(self.service.store.runtime_dir / "processing-scheduler.json")
        terminate_tree(owner["pid"], 2)
        self.service = ManagerService(self.root)
        state = self.release_and_wait(processing_id)
        self.assertEqual(state["status"], "completed", state)

    def test_dispatcher_waits_for_daily_time_and_serializes_jobs(self):
        _, processing_id = self.capture()
        self.service.start_task = Mock()
        self.assertTrue(dispatch_once(self.service))
        self.service.start_task.assert_not_called()
        state = self.service.store.read_state(processing_id)
        state.update(status="starting", runner_pid=None)
        self.service.store.write_state(processing_id, state)
        self.assertTrue(dispatch_once(self.service))
        self.service.start_task.assert_not_called()

    def test_eternal_queue_waits_before_processing(self):
        self.configure_deferred()
        marker = self.root / "batch.ready.yaml"
        save_yaml(marker, {"queued_at": now_iso()})
        workflow = EternalWorkflow.__new__(EternalWorkflow)
        workflow.queue_dir = self.root
        workflow.runtime = Mock(
            paths=self.service.paths, project=self.service.config.project
        )
        workflow.runtime.hard_stop.is_set.return_value = False
        workflow.task = {"processing": {"enabled": True}}
        workflow._drain_queue = Mock()
        workflow._drain_queue.is_set.return_value = True
        workflow._processor_failures = []
        workflow._batch_processor = Mock()
        with (
            patch(
                "timelapse_manager.workflows.eternal.processing_ready",
                side_effect=[False, True],
            ),
            patch("timelapse_manager.workflows.eternal.time.sleep") as sleep,
        ):
            workflow._processing_loop()
        sleep.assert_called_once()
        workflow._batch_processor.process.assert_called_once()
        self.assertFalse(marker.exists())
