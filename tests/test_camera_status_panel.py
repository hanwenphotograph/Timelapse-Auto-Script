from __future__ import annotations

import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch

from timelapse_manager.camera import CameraConnection
from timelapse_manager.ui.camera_status import CameraStatusPanel


class CameraStatusPanelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.panel = CameraStatusPanel.__new__(CameraStatusPanel)
        self.panel.root_path = Path("/private/app")
        self.panel._results = Queue()
        self.panel._busy = False
        self.panel._closed = False
        self.panel._poll_id = None
        self.panel.refresh_button = Mock()
        self.panel.state_label = Mock()
        self.panel.detail_label = Mock()
        self.panel.checked_label = Mock()
        self.panel.after = Mock(return_value="poll")
        self.panel.after_cancel = Mock()

    def test_duplicate_refresh_does_not_spawn_multiple_probes(self) -> None:
        with patch("timelapse_manager.ui.camera_status.threading.Thread") as thread:
            self.panel.refresh()
            self.panel.refresh()
        self.assertEqual(thread.call_count, 1)
        self.assertTrue(self.panel._busy)
        self.panel.refresh_button.configure.assert_called_once_with(state="disabled")

    def test_worker_queues_results_without_accessing_tk(self) -> None:
        connection = CameraConnection("disconnected", "No camera")
        with (
            patch("timelapse_manager.ui.camera_status.threading.Thread") as thread,
            patch(
                "timelapse_manager.ui.camera_status.detect_connection",
                return_value=connection,
            ),
        ):
            self.panel.refresh()
            calls = self.panel.state_label.configure.call_count
            thread.call_args.kwargs["target"]()
        self.assertEqual(self.panel.state_label.configure.call_count, calls)
        self.assertEqual(self.panel._results.get_nowait(), connection)

    def test_error_result_restores_refresh_button_and_displays_error(self) -> None:
        self.panel._busy = True
        self.panel._results.put(CameraConnection("error", "Detection timed out"))
        self.panel._poll_result()
        self.assertFalse(self.panel._busy)
        self.panel.refresh_button.configure.assert_called_once_with(state="normal")
        self.panel.detail_label.configure.assert_called_once_with(
            text="Detection timed out"
        )

    def test_closing_during_detection_cancels_poll_and_discards_late_result(
        self,
    ) -> None:
        self.panel._poll_id = "pending-poll"
        self.panel.close()
        self.panel._results.put(CameraConnection("connected", "Camera"))
        self.panel._poll_result()
        self.panel.after_cancel.assert_called_once_with("pending-poll")
        self.panel.state_label.configure.assert_not_called()
        self.panel.refresh_button.configure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
