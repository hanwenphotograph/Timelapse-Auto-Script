"""Structured overall and subtask progress rows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from timelapse_manager.ui.progress_values import (
    active_schedule_value,
    capture_bounds,
    local_naive,
    overall_value,
    progress_value,
)


_STATUS_LABELS = {
    "idle": "未启动",
    "starting": "正在启动",
    "running": "运行中",
    "finishing": "收尾中",
    "stopping": "停止中",
    "completed": "已完成",
    "failed": "失败",
    "stopped": "已停止",
    "exited": "已退出",
}
_ROLE_LABELS = {
    "runner": "任务工作进程",
    "camera-timelapse": "相机拍摄",
    "camera-timelapse-eternal": "相机拍摄",
    "bracketlapse-standby": "后期处理",
    "bracketlapse-process": "后期处理",
    "sunsetscore": "晚霞评分",
    "sunsetscore-resident": "晚霞评分服务",
    "archive": "归档",
}


@dataclass(frozen=True, slots=True)
class ProgressItem:
    """One progress-bar row; ``None`` means indeterminate progress."""

    key: str
    label: str
    status: str
    detail: str
    value: float | None


def task_progress_items(
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[ProgressItem, ...]:
    """Build an overall row followed by independently tracked subtask rows."""
    moment = local_naive(now or datetime.now())
    items = [_overall_item(task, state, moment)]
    progress = state.get("progress")
    nested = progress if isinstance(progress, Mapping) else {}
    index = 0
    for source in ("children", "threads", "subtasks"):
        records = state.get(source) or nested.get(source)
        for record in _records(records):
            items.append(_subtask_item(task, state, record, source, index, moment))
            index += 1
    return tuple(items)


def _overall_item(
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    now: datetime,
) -> ProgressItem:
    status = str(state.get("status", "idle"))
    phase = str(state.get("phase") or _STATUS_LABELS.get(status, "等待中"))
    explicit = overall_value(state)
    if status == "completed":
        value = 1.0
    elif status in {"idle", "failed", "stopped", "exited"}:
        value = explicit if explicit is not None else 0.0
    elif explicit is not None:
        value = explicit
    elif task.get("preset") == "eternal" or status in {
        "starting",
        "finishing",
        "stopping",
    }:
        value = None
    else:
        bounds = capture_bounds(task)
        value = active_schedule_value(bounds, now)
        if bounds is not None and now < bounds[0]:
            phase = f"距开始 {_duration_label(bounds[0] - now)}"
    return ProgressItem("overall", "总体进度", status, phase, value)


def _subtask_item(
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    record: Mapping[str, Any],
    source: str,
    index: int,
    now: datetime,
) -> ProgressItem:
    role = str(record.get("role") or record.get("name") or record.get("id") or "子任务")
    status = str(record.get("status") or "running")
    pid = record.get("pid")
    label = _role_label(role)
    if pid:
        label = f"{label} · PID {pid}"
    detail = str(record.get("phase") or record.get("message") or "")
    state_phase = str(state.get("phase") or "")
    if not detail and _phase_matches(role, state_phase):
        detail = state_phase
    if not detail:
        detail = _STATUS_LABELS.get(status, status)
    value = progress_value(record)
    if status == "completed":
        value = 1.0
    elif value is None and status in {
        "idle",
        "waiting",
        "queued",
        "failed",
        "stopped",
        "exited",
    }:
        value = 0.0
    elif value is None and role.startswith("camera-timelapse"):
        value = active_schedule_value(capture_bounds(task), now)
    identity = record.get("id") or pid or f"{role}-{index}"
    return ProgressItem(f"{source}-{identity}", label, status, detail, value)


def _records(value: object) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        return tuple(
            {**record, "name": record.get("name") or str(name)}
            for name, record in value.items()
            if isinstance(record, Mapping)
        )
    if isinstance(value, (list, tuple)):
        return tuple(record for record in value if isinstance(record, Mapping))
    return ()


def _role_label(role: str) -> str:
    if role.startswith("bracketlapse-batch-"):
        return f"后期处理 · 批次 {role.rsplit('-', 1)[-1]}"
    return _ROLE_LABELS.get(role, role)


def _phase_matches(role: str, phase: str) -> bool:
    if role.startswith("camera-timelapse"):
        return "拍摄" in phase
    if role.startswith("bracketlapse"):
        return any(word in phase for word in ("后期", "HDR", "去闪", "视频"))
    if role.startswith("sunsetscore"):
        return "晚霞" in phase
    return False


def _duration_label(value: timedelta) -> str:
    minutes = max(0, int(value.total_seconds() // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}小时{minutes:02d}分" if hours else f"{minutes}分"
