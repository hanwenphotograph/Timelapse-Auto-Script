from __future__ import annotations

import subprocess
import unittest

from timelapse_manager.dependency_manager.build_info import inspect_build_info
from timelapse_manager.dependency_manager.models import DependencyBuildInfo


class DependencyBuildInfoTests(unittest.TestCase):
    def test_public_json_is_parsed(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            (
                '{"version":"0.3.0","branch":"master",'
                '"commit":"abc123","build_time":"2026-08-08T12:30:00Z"}'
            ),
            "",
        )

        info = inspect_build_info(
            ("/tools/bracketlapse",), run=lambda *_args, **_kwargs: completed
        )

        self.assertEqual(
            info,
            DependencyBuildInfo(
                "0.3.0", "master", "2026-08-08T12:30:00Z", "abc123"
            ),
        )

    def test_unsupported_or_invalid_metadata_is_ignored(self) -> None:
        unsupported = subprocess.CompletedProcess([], 2, "", "unknown option")
        invalid = subprocess.CompletedProcess(
            [],
            0,
            '{"version":"0.3.0","build_time":"2026-08-08 12:30:00"}',
            "",
        )

        self.assertIsNone(
            inspect_build_info(("tool",), run=lambda *_args, **_kwargs: unsupported)
        )
        self.assertIsNone(
            inspect_build_info(("tool",), run=lambda *_args, **_kwargs: invalid)
        )

    def test_summary_formats_utc_build_time(self) -> None:
        info = DependencyBuildInfo(
            "0.11.0", "main", "2026-08-08T20:45:30+08:00", "abc123"
        )

        self.assertEqual(
            info.summary,
            "版本 0.11.0 · 分支 main · 构建 2026-08-08 12:45 UTC",
        )

    def test_summary_compacts_long_branch_without_losing_source_value(self) -> None:
        branch = "feature/package-build-information-with-a-very-long-name"
        info = DependencyBuildInfo("0.11.0", branch)

        self.assertEqual(info.branch, branch)
        self.assertIn("分支 feature/package-build-informa...", info.summary)


if __name__ == "__main__":
    unittest.main()
