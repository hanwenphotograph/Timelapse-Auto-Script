"""Task progress labels displayed in GUI tables."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any


_ACTIVE_STATUSES = {"running", "finishing", "stopping"}
_TERMINAL_LABELS = {
    "completed": "已完成",
    "failed": "失败",
    "stopped": "已停止",
    "exited": "已退出",
}
_BAR_SEGMENTS = 12


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
    """Return a compact, human-readable progress label for a task row."""
    status = str(state.get("status", "idle"))
    if status in _TERMINAL_LABELS:
        return _TERMINAL_LABELS[status]
    if status == "idle":
        return "未启动"
    if status == "starting":
        return "正在启动"
    if task.get("preset") == "eternal":
        return _eternal_progress_label(state)
    if status not in _ACTIVE_STATUSES:
        return str(state.get("phase") or "等待中")
    bounds = _capture_bounds(task)
    if bounds is None:
        return str(state.get("phase") or "运行中")
    return _scheduled_progress_label(*bounds, state=state, now=now or datetime.now())


def _capture_bounds(task: Mapping[str, Any]) -> tuple[datetime, datetime] | None:
    capture = task.get("capture")
    if not isinstance(capture, Mapping):
        return None
    keys = ("start_date", "start_at", "end_date", "end_at")
    values = [capture.get(key) for key in keys]
    if not all(isinstance(value, str) and value for value in values):
        return None
    try:
        start = datetime.fromisoformat(f"{values[0]}T{values[1]}")
        end = datetime.fromisoformat(f"{values[2]}T{values[3]}")
    except ValueError:
        return None
    return (start, end) if end > start else None


def _scheduled_progress_label(
    start: datetime,
    end: datetime,
    *,
    state: Mapping[str, Any],
    now: datetime,
) -> str:
    total = end - start
    if now < start:
        return f"距开始 {_duration_label(start - now)}"
    ratio = min(1.0, max(0.0, (now - start) / total))
    percent = round(ratio * 100)
    if ratio >= 1:
        detail = str(state.get("phase") or "拍摄时段已结束")
        return f"{_progress_bar(percent)} {percent}% · {detail}"
    if state.get("status") == "finishing":
        detail = "正在收尾"
    elif state.get("status") == "stopping":
        detail = "正在停止"
    else:
        return f"{_progress_bar(percent)} {percent}%"
    return f"{_progress_bar(percent)} {percent}% · {detail}"


def _eternal_progress_label(state: Mapping[str, Any]) -> str:
    progress = state.get("progress")
    if not isinstance(progress, Mapping):
        progress = {}
    batches = _nonnegative_count(progress.get("eternal_batches"))
    pending = _nonnegative_count(progress.get("eternal_pending_groups"))
    queued = _nonnegative_count(progress.get("eternal_queue"))
    archiving = _nonnegative_count(progress.get("eternal_archives"))
    parts = ["持续运行"]
    if batches:
        parts.append(f"已归档 {batches} 批")
    if pending:
        parts.append(f"待归档 {pending} 组")
    if archiving:
        parts.append(f"归档中 {archiving} 批")
    if queued:
        parts.append(f"待处理 {queued} 批")
    return " · ".join(parts)


def _nonnegative_count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _progress_bar(percent: int) -> str:
    filled = min(_BAR_SEGMENTS, max(0, round(percent * _BAR_SEGMENTS / 100)))
    return "█" * filled + "░" * (_BAR_SEGMENTS - filled)


def _duration_label(value: timedelta) -> str:
    minutes = max(0, int(value.total_seconds() // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}小时{minutes:02d}分" if hours else f"{minutes}分"
