"""Prevent overlapping capture tasks and competing writers across task chains."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from timelapse_manager.errors import TaskError
from timelapse_manager.process_utils import process_matches
from timelapse_manager.task_store import ACTIVE_STATUSES, TaskStore


def _work_dir(store: TaskStore, task: dict[str, Any]) -> Path | None:
    value = task.get("capture", {}).get("work_dir")
    return store.config.paths.resolve_from_root(str(value)) if value else None


def _window(task: dict[str, Any]) -> tuple[datetime, datetime] | None:
    capture = task.get("capture", {})
    try:
        return tuple(
            datetime.fromisoformat(f"{capture[key + '_date']}T{capture[key + '_at']}")
            for key in ("start", "end")
        )
    except (KeyError, TypeError, ValueError):
        return None


def validate_resources(store: TaskStore, task: dict[str, Any]) -> None:
    work_dir = _work_dir(store, task)
    window = _window(task)
    now = datetime.now()
    for other in store.list_definitions():
        if other.get("_error"):
            continue
        state = store.read_state(other["id"], reconcile=True)
        live_children = [
            child
            for child in state.get("children", [])
            if process_matches(child.get("pid"), child.get("created_at"))
        ]
        if other["id"] == task["id"]:
            if state["status"] not in ACTIVE_STATUSES and live_children:
                raise TaskError("上次任务仍有子进程运行，请先停止残留进程")
            continue
        if state["status"] not in ACTIVE_STATUSES and not live_children:
            continue
        if work_dir is not None and work_dir == _work_dir(store, other):
            raise TaskError(f"工作目录已有活动任务，不能重复拍摄或处理：{other['id']}")
        other_window = _window(other)
        # Expired tasks can resume processing without reserving the camera.
        if (window and window[1] <= now) or (other_window and other_window[1] <= now):
            continue
        if state["status"] not in ACTIVE_STATUSES and not any(
            child.get("role") == "camera-timelapse" for child in live_children
        ):
            continue
        if (
            window is None
            or other_window is None
            or (window[0] < other_window[1] and other_window[0] < window[1])
        ):
            raise TaskError(
                f"拍摄时段与活动任务冲突，相机不能被重复占用：{other['id']}"
            )
