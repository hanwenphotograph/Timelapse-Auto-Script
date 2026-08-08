from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from timelapse_manager.dependency_manager.catalog import CATALOG_BY_ID
from timelapse_manager.dependency_manager.models import DependencyStatus
from timelapse_manager.ui.package_page import PackagePage


class _ImmediateThread:
    def __init__(self, *, target, **_kwargs) -> None:
        self.target = target

    def start(self) -> None:
        self.target()


class PackageBranchSelectionTests(unittest.TestCase):
    def test_selected_branch_reaches_confirmation_and_install(self) -> None:
        manager = Mock()
        manager.confirmation.return_value = "confirm"
        page = object.__new__(PackagePage)
        page._busy = False
        page._closed = False
        page.root = None
        page.manager = manager
        page.notify = Mock()
        page._rows = {
            "bracketlapse": Mock(selected_branch="dev_deflick"),
        }
        page._statuses = [
            DependencyStatus(
                CATALOG_BY_ID["bracketlapse"],
                "ready",
                "/tools/bracketlapse",
            )
        ]
        page._set_busy = Mock()
        page._after = lambda operation: operation()
        page._install_finished = Mock()

        with (
            patch(
                "timelapse_manager.ui.package_page.messagebox.askyesno",
                return_value=True,
            ),
            patch(
                "timelapse_manager.ui.package_page.threading.Thread",
                _ImmediateThread,
            ),
        ):
            page.install("bracketlapse")

        manager.confirmation.assert_called_once_with("bracketlapse", "dev_deflick")
        self.assertEqual(manager.install.call_args.kwargs["branch"], "dev_deflick")


if __name__ == "__main__":
    unittest.main()
