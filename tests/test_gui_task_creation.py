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

    def test_webhook_action_saves_before_sending(self) -> None:
        self.app._current_config_kind = "webhook"
        self.app._save_current_config = Mock(return_value=True)

        self.app.test_webhook()

        self.app._save_current_config.assert_called_once_with(show_confirmation=False)
        label, operation = self.app._async_action.call_args.args
        self.assertEqual(label, "Webhook 测试推送")
        operation()
        self.app.service.test_webhook.assert_called_once_with()

    def test_webhook_button_is_only_visible_for_webhook_config(self) -> None:
        self.app.test_webhook_button = Mock()
        self.app._current_config_kind = "project"

        self.app._update_config_actions()

        self.app.test_webhook_button.grid_remove.assert_called_once_with()
        self.app._current_config_kind = "webhook"
        self.app._update_config_actions()
        self.app.test_webhook_button.grid.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
