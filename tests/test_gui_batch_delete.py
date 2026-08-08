from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from timelapse_manager.ui.app import TimelapseApp
from timelapse_manager.ui.task_deletion import delete_tasks


class BatchDeletionTests(unittest.TestCase):
    def test_delete_tasks_continues_after_a_failure(self) -> None:
        operation = Mock(side_effect=[None, RuntimeError("任务正在运行"), None])

        result = delete_tasks(("task-a", "task-b", "task-c"), operation)

        self.assertEqual(result.deleted, ("task-a", "task-c"))
        self.assertEqual(result.failures, (("task-b", "任务正在运行"),))
        self.assertEqual(
            operation.call_args_list,
            [call("task-a"), call("task-b"), call("task-c")],
        )

    def test_delete_tasks_only_attempts_duplicate_id_once(self) -> None:
        operation = Mock()

        result = delete_tasks(("task-a", "task-a"), operation)

        operation.assert_called_once_with("task-a")
        self.assertEqual(result.deleted, ("task-a",))


class GuiBatchDeletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = TimelapseApp.__new__(TimelapseApp)
        self.app.root = Mock()
        self.app.service = Mock()
        self.app.task_table = Mock()
        self.app.refresh_all = Mock()
        self.app._set_status = Mock()

    @patch("timelapse_manager.ui.app.messagebox")
    def test_selected_tasks_are_deleted_with_runtime_data(
        self, messagebox: Mock
    ) -> None:
        self.app.task_table.selected_ids.return_value = ("task-a", "task-b")
        messagebox.askyesnocancel.return_value = True

        self.app.delete_task()

        self.assertEqual(
            self.app.service.delete_task.call_args_list,
            [
                call("task-a", purge_runtime=True),
                call("task-b", purge_runtime=True),
            ],
        )
        self.app.refresh_all.assert_called_once_with()
        self.app._set_status.assert_called_once_with("已删除 2 个任务")
        messagebox.showerror.assert_not_called()

    @patch("timelapse_manager.ui.app.messagebox")
    def test_cancel_keeps_all_selected_tasks(self, messagebox: Mock) -> None:
        self.app.task_table.selected_ids.return_value = ("task-a", "task-b")
        messagebox.askyesnocancel.return_value = None

        self.app.delete_task()

        self.app.service.delete_task.assert_not_called()
        self.app.refresh_all.assert_not_called()

    @patch("timelapse_manager.ui.app.messagebox")
    def test_empty_selection_does_not_open_confirmation(self, messagebox: Mock) -> None:
        self.app.task_table.selected_ids.return_value = ()

        self.app.delete_task()

        messagebox.askyesnocancel.assert_not_called()
        self.app._set_status.assert_called_once_with("请先选择要删除的任务", "warning")

    @patch("timelapse_manager.ui.app.messagebox")
    def test_partial_failure_is_reported_after_other_deletions(
        self, messagebox: Mock
    ) -> None:
        self.app.task_table.selected_ids.return_value = ("task-a", "task-b")
        self.app.service.delete_task.side_effect = [
            RuntimeError("请先停止任务，再删除任务"),
            None,
        ]
        messagebox.askyesnocancel.return_value = False

        self.app.delete_task()

        self.assertEqual(self.app.service.delete_task.call_count, 2)
        self.app.refresh_all.assert_called_once_with()
        title, body = messagebox.showerror.call_args.args
        self.assertEqual(title, "部分任务删除失败")
        self.assertIn("task-a：请先停止任务，再删除任务", body)
        self.app._set_status.assert_called_once_with(
            "已删除 1 个任务，1 个任务删除失败", "warning"
        )

    def test_single_task_actions_reject_multiple_selection(self) -> None:
        self.app.task_table.selected_ids.return_value = ("task-a", "task-b")

        result = self.app._require_task()

        self.assertIsNone(result)
        self.app._set_status.assert_called_once_with(
            "此操作一次只能处理一个任务，请仅选择一个任务", "warning"
        )

    def test_select_all_selects_every_visible_task(self) -> None:
        self.app.task_table.tree.get_children.return_value = ("task-a", "task-b")
        self.app._selection_changed = Mock()

        result = self.app.select_all_tasks()

        self.assertEqual(result, "break")
        self.app.task_table.tree.selection_set.assert_called_once_with(
            "task-a", "task-b"
        )
        self.app.task_table.tree.focus.assert_called_once_with("task-a")
        self.app._selection_changed.assert_called_once_with()

    def test_refresh_preserves_multiple_selection(self) -> None:
        self.app.refresh_all = TimelapseApp.refresh_all.__get__(self.app)
        items = [
            {
                "task": {"id": task_id, "name": task_id, "preset": "manual"},
                "state": {"status": "idle"},
            }
            for task_id in ("task-a", "task-b")
        ]
        self.app.service.list_tasks.return_value = items
        self.app.service.list_processes.return_value = []
        self.app.task_table.selected_ids.return_value = ("task-a", "task-b")
        self.app.task_table.tree.exists.return_value = True
        self.app.overview_table = Mock()
        self.app.selected_task_value = Mock()
        self.app.log_task_value = Mock()
        self.app._task_ids = []
        self.app._populate_processes = Mock()
        self.app._update_summary = Mock()
        self.app._update_log_choices = Mock()

        self.app.refresh_all()

        self.app.task_table.tree.selection_set.assert_called_once_with(
            "task-a", "task-b"
        )
        self.app.selected_task_value.set.assert_called_with("已选择 2 个任务")


if __name__ == "__main__":
    unittest.main()
