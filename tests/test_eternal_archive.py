from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from timelapse_manager.io_utils import load_yaml
from timelapse_manager.workflows.eternal import EternalWorkflow


class DummyRuntime:
    def __init__(self, root: Path):
        self.task = {
            "id": "archive-test",
            "eternal": {"batch_groups": 2, "images_per_group": 3, "state_dir": None},
            "capture": {"interval_seconds": None},
            "processing": {"enabled": True},
            "cleanup": {"enabled": False, "delete_incomplete_groups": False},
            "retry": {"delay_seconds": 0},
        }
        self.project = {
            "eternal": {
                "batch_groups": 2,
                "images_per_group": 3,
                "archive_retry_seconds": 0,
                "queue_poll_seconds": 0.1,
            }
        }
        self.paths = SimpleNamespace(
            resolve_from_root=lambda value: (root / value).resolve()
        )
        self.auto_root = root / "output"
        self.progress: dict = {}
        self.finish_after_current = threading.Event()

    def set_progress(self, **values) -> None:
        self.progress.update(values)

    def log(self, _message: str) -> None:
        return

    def notify_async(self, _event: str, _content: str) -> None:
        return


class EternalArchiveTests(unittest.TestCase):
    def test_dispatched_groups_remain_reserved_until_archive_completes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = DummyRuntime(Path(temp_dir))
            workflow = EternalWorkflow(runtime)  # type: ignore[arg-type]
            workflow.state_dir.mkdir(parents=True)
            workflow.capture_dir.mkdir()
            workflow.queue_dir.mkdir()
            workflow.counter_file.write_text("0\n", encoding="ascii")
            for group in (1, 2):
                for exposure in range(3):
                    (workflow.capture_dir / f"{group:04d}_{exposure}.jpg").write_bytes(
                        b"raw"
                    )
                workflow._pending.append({"group": group, "completed_at": 1.0})
                workflow._known_groups.add(group)
            workflow._save_pending()

            workflow._dispatch_batch(2, full_batch=True)

            self.assertEqual(workflow._pending, [])
            self.assertEqual(workflow._known_groups, {1, 2})
            manifest = workflow._archive_queue.get_nowait()
            workflow._complete_archive(manifest, load_yaml(manifest))
            self.assertEqual(workflow._known_groups, set())
            self.assertTrue((workflow.queue_dir / "00000001.ready.yaml").exists())


if __name__ == "__main__":
    unittest.main()
