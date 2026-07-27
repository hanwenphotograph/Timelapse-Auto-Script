from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from timelapse_manager.sunset_score.availability import detect_sunset_score


class SunsetScoreAvailabilityTests(unittest.TestCase):
    @patch(
        "timelapse_manager.sunset_score.availability.resolve_command",
        return_value=["/tools/sunsetscore"],
    )
    def test_supported_version_enables_scoring(self, _resolve) -> None:
        completed = subprocess.CompletedProcess([], 0, "sunsetscore 0.9.0\n", "")
        result = detect_sunset_score(
            "sunsetscore", run=lambda *_args, **_kwargs: completed
        )
        self.assertTrue(result.enabled)
        self.assertEqual(result.version, "0.9.0")

    @patch(
        "timelapse_manager.sunset_score.availability.resolve_command",
        return_value=["/tools/sunsetscore"],
    )
    def test_old_version_is_automatically_disabled(self, _resolve) -> None:
        completed = subprocess.CompletedProcess([], 0, "sunsetscore 0.8.9\n", "")
        result = detect_sunset_score(
            "sunsetscore", run=lambda *_args, **_kwargs: completed
        )
        self.assertFalse(result.enabled)
        self.assertIn("低于最低要求", result.reason)

    @patch(
        "timelapse_manager.sunset_score.availability.resolve_command",
        side_effect=OSError("missing"),
    )
    def test_missing_command_is_automatically_disabled(self, _resolve) -> None:
        result = detect_sunset_score("sunsetscore")
        self.assertFalse(result.enabled)
        self.assertIn("未找到命令", result.reason)

    @patch(
        "timelapse_manager.sunset_score.availability.resolve_command",
        return_value=["/tools/sunsetscore"],
    )
    def test_unparseable_version_is_automatically_disabled(self, _resolve) -> None:
        completed = subprocess.CompletedProcess([], 0, "unknown version\n", "")
        result = detect_sunset_score(
            "sunsetscore", run=lambda *_args, **_kwargs: completed
        )
        self.assertFalse(result.enabled)
        self.assertIn("无法解析版本", result.reason)

    @patch(
        "timelapse_manager.sunset_score.availability.resolve_command",
        return_value=["/tools/sunsetscore"],
    )
    def test_version_probe_timeout_is_automatically_disabled(self, _resolve) -> None:
        def timeout(*_args, **_kwargs):
            raise subprocess.TimeoutExpired("sunsetscore", 10)

        result = detect_sunset_score("sunsetscore", run=timeout)
        self.assertFalse(result.enabled)
        self.assertIn("超过 10 秒", result.reason)


if __name__ == "__main__":
    unittest.main()
