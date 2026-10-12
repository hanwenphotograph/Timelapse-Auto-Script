from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from timelapse_manager.errors import TaskError
from timelapse_manager.runtime_storage import StorageGuard


class RuntimeStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.log, self.notify = Mock(), Mock()
        self.guard = StorageGuard(
            [self.root / "new-output", self.root], 35, self.log, self.notify
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_critical_space_stops_work_before_disk_exhaustion(self) -> None:
        with patch("timelapse_manager.runtime_storage.disk_free_gb", return_value=0.5):
            with self.assertRaisesRegex(TaskError, "保留原片"):
                self.guard.check()

    def test_warning_does_not_stop_work_or_repeat_for_same_volume(self) -> None:
        with (
            patch(
                "timelapse_manager.runtime_storage.disk_free_gb", return_value=20
            ) as free,
            patch(
                "timelapse_manager.runtime_storage.time.monotonic",
                side_effect=[0, 6, 12],
            ),
        ):
            for _ in range(3):
                self.guard.check()
        self.assertEqual(free.call_count, 3)
        self.assertEqual(self.notify.call_count, 1)

    def test_checks_are_throttled_and_warning_resets_after_space_recovers(self) -> None:
        with (
            patch(
                "timelapse_manager.runtime_storage.disk_free_gb",
                side_effect=[20, 40, 20],
            ) as free,
            patch(
                "timelapse_manager.runtime_storage.time.monotonic",
                side_effect=[0, 1, 6, 12],
            ),
        ):
            for _ in range(4):
                self.guard.check()
        self.assertEqual(free.call_count, 3)
        self.assertEqual(self.notify.call_count, 2)


if __name__ == "__main__":
    unittest.main()
