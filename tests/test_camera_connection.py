from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from timelapse_manager.camera.connection import detect_connection, parse_devices
from timelapse_manager.errors import ProcessError
from tests.managed_dependency_support import install_fake_native_tools


class CameraConnectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = install_fake_native_tools(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_parses_multiple_models_and_transports_without_table_headers(self) -> None:
        devices = parse_devices(
            "Model                          Port\n"
            "----------------------------------------------------------\n"
            "Canon EOS R5                   usb:001,003\n"
            "Sony Alpha ILCE-7M4            usb:001,004\n"
            "Network Camera                ptpip:192.168.1.2\n"
            "Canon EOS R5                   usb:001,003\n"
        )
        self.assertEqual(len(devices), 3)
        self.assertEqual(devices[0].model, "Canon EOS R5")
        self.assertEqual(devices[1].port, "usb:001,004")
        self.assertEqual(devices[2].port, "ptpip:192.168.1.2")

    def test_connected_uses_only_private_read_only_detection_command(self) -> None:
        completed = subprocess.CompletedProcess(
            [], 0, "Canon EOS R5                   usb:001,003\n", ""
        )
        with patch(
            "timelapse_manager.camera.connection.subprocess.run", return_value=completed
        ) as run:
            connection = detect_connection(self.root)

        self.assertEqual(connection.status, "connected")
        self.assertEqual(len(connection.devices), 1)
        self.assertIn("Canon EOS R5", connection.message)
        self.assertTrue(connection.checked_at)
        args, kwargs = run.call_args
        self.assertEqual(args[0][1:], ["--auto-detect"])
        self.assertTrue(Path(args[0][0]).is_relative_to(self.paths.root))
        self.assertEqual(kwargs["env"]["LC_ALL"], "C")
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)

    def test_empty_table_means_disconnected(self) -> None:
        with patch(
            "timelapse_manager.camera.connection.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 0, "Model    Port\n----\n", ""
            ),
        ):
            connection = detect_connection(self.root)
        self.assertEqual(connection.status, "disconnected")
        self.assertEqual(connection.devices, ())

    def test_missing_dependency_is_distinct_from_no_camera(self) -> None:
        with (
            patch(
                "timelapse_manager.camera.connection.resolve_command",
                side_effect=ProcessError("missing"),
            ),
            patch("timelapse_manager.camera.connection.subprocess.run") as run,
        ):
            connection = detect_connection(self.root)
        self.assertEqual(connection.status, "unavailable")
        run.assert_not_called()

    def test_timeout_and_execution_errors_are_distinct_from_no_camera(self) -> None:
        for error in (
            subprocess.TimeoutExpired("gphoto2", 10),
            OSError("cannot execute"),
        ):
            with (
                self.subTest(error=type(error).__name__),
                patch(
                    "timelapse_manager.camera.connection.subprocess.run",
                    side_effect=error,
                ),
            ):
                self.assertEqual(detect_connection(self.root).status, "error")

    def test_failed_detection_does_not_report_disconnected_or_connected(self) -> None:
        with patch(
            "timelapse_manager.camera.connection.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 1, "Canon EOS R5  usb:001,003\n", "USB detection failed"
            ),
        ):
            connection = detect_connection(self.root)
        self.assertEqual(connection.status, "error")
        self.assertIn("USB detection failed", connection.message)


if __name__ == "__main__":
    unittest.main()
