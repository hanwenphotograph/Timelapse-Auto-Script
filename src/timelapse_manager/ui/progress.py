"""Task progress summaries displayed in GUI tables and controls."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from timelapse_manager.ui.progress_model import ProgressItem, task_progress_items
from timelapse_manager.ui.progress_stage import resolve_main_progress
from timelapse_manager.ui.progress_values import local_naive


_TERMINAL_LABELS = {
    "completed": "已完成",
    "failed": "失败",
    "stopped": "已停止",
    "exited": "已退出",
}


def compact_timestamp(value: object) -> str:
    """Format a persisted timestamp for a compact table cell."""
    if not isinstance(value, str) or not value:
        return ""
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value[:16]
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone()
    return timestamp.strftime("%Y-%m-%d %H:%M")


def task_progress_label(
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> str:
    """Return compact progress text without simulating a progress bar."""
    status = str(state.get("status", "idle"))
    if status in _TERMINAL_LABELS:
        return _TERMINAL_LABELS[status]
    if status == "idle":
        return "未启动"
    if status == "starting":
        return "正在启动"
    if task.get("preset") == "eternal":
        return _eternal_progress_label(state)
    if status not in {"running", "finishing", "stopping"}:
        return str(state.get("phase") or "等待中")
    moment = local_naive(now or datetime.now())
    main = resolve_main_progress(task, state, moment)
    if main.stage == "waiting_capture" or main.value is None:
        return main.label
    return f"{main.label} {round(main.value * 100)}%"


def _eternal_progress_label(state: Mapping[str, Any]) -> str:
    progress = state.get("progress")
    values = progress if isinstance(progress, Mapping) else {}
    parts = ["持续运行"]
    for key, label, suffix in (
        ("eternal_batches", "已归档", "批"),
        ("eternal_pending_groups", "待归档", "组"),
        ("eternal_archives", "归档中", "批"),
        ("eternal_queue", "待处理", "批"),
    ):
        count = values.get(key)
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            parts.append(f"{label} {count} {suffix}")
    return " · ".join(parts)


__all__ = [
    "ProgressItem",
    "compact_timestamp",
    "task_progress_items",
    "task_progress_label",
]
