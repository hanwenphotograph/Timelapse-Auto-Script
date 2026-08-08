from __future__ import annotations

import unittest
from io import BytesIO
from pathlib import Path
from urllib.error import URLError

from timelapse_manager.dependency_manager.installation import DependencyInstaller
from timelapse_manager.dependency_manager.sources import (
    inspect_remote_branches,
    package_install_url,
    validate_branch,
)


class DependencyBranchTests(unittest.TestCase):
    def test_remote_branches_put_configured_default_first(self) -> None:
        response = BytesIO(
            b'[{"name":"dev_deflick"},{"name":"master"},'
            b'{"name":"feature/build-info"}]'
        )

        branches = inspect_remote_branches(
            "bracketlapse", open_url=lambda *_args, **_kwargs: response
        )

        self.assertEqual(
            branches,
            ("master", "dev_deflick", "feature/build-info"),
        )

    def test_branch_probe_failure_falls_back_to_primary_branch(self) -> None:
        def fail(*_args: object, **_kwargs: object) -> object:
            raise URLError("network failed")

        branches = inspect_remote_branches(
            "bracketlapse", open_url=fail
        )

        self.assertEqual(branches, ("master",))

    def test_selected_branch_is_encoded_in_install_url(self) -> None:
        self.assertEqual(
            package_install_url("bracketlapse", "feature/ui#1"),
            (
                "https://github.com/hanwenphotograph/Bracketlapse/"
                "archive/refs/heads/feature/ui%231.tar.gz"
            ),
        )

    def test_invalid_branch_is_rejected(self) -> None:
        for value in ("", "../main", "bad branch", "main~1", "topic.lock"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_branch(value)

    def test_install_plan_uses_selected_branch_and_names_it(self) -> None:
        plan = DependencyInstaller(Path.cwd()).plan(
            "python:bracketlapse",
            {},
            branch="dev_deflick",
        )

        assert plan is not None
        self.assertTrue(
            plan.command[-1].endswith(
                "Bracketlapse/archive/refs/heads/dev_deflick.tar.gz"
            )
        )
        self.assertIn("源码分支：dev_deflick", plan.confirmation)


if __name__ == "__main__":
    unittest.main()
