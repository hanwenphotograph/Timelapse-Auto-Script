from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from timelapse_manager.ui.app import TimelapseApp


class GuiTaskCreationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = TimelapseApp.__new__(TimelapseApp)
        self.app.root = Mock()
        self.app.service = Mock()
        self.app.service.create_task.return_value = {"id": "created-task"}
        self.app.show_page = Mock()
        self.app.refresh_all = Mock()
        self.app.edit_task = Mock()
        self.app._async_action = Mock()

    @patch("timelapse_manager.ui.app.NewTaskDialog")
    def test_scheduled_task_starts_after_creation(self, dialog_type: Mock) -> None:
        dialog_type.return_value.result = ("清晨任务", "scheduled_loop")

        self.app.create_task()

        self.app.service.create_task.assert_called_once_with(
            "清晨任务", "scheduled_loop"
        )
        self.app.refresh_all.assert_called_once_with(select="created-task")
        self.app.edit_task.assert_not_called()
        label, operation = self.app._async_action.call_args.args
        self.assertEqual(label, "自动启动任务")
        operation()
        self.app.service.start_task.assert_called_once_with("created-task")

    @patch("timelapse_manager.ui.app.NewTaskDialog")
    def test_manual_task_opens_editor_without_starting(self, dialog_type: Mock) -> None:
        dialog_type.return_value.result = ("手动任务", "manual")

        self.app.create_task()

        self.app.service.create_task.assert_called_once_with("手动任务", "manual")
        self.app.edit_task.assert_called_once_with("created-task")
        self.app._async_action.assert_not_called()
        self.app.service.start_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
