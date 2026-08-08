"""Structured main-stage and feature progress rows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from timelapse_manager.ui.progress_stage import (
    MainProgress,
    is_bracket_role,
    progress_records,
    record_stage,
    resolve_main_progress,
)
from timelapse_manager.ui.progress_values import (
    local_naive,
    progress_counts,
    progress_value,
)


_TERMINAL_DETAILS = {
    "idle": "未启动",
    "completed": "已完成",
    "failed": "失败",
    "stopped": "已停止",
    "exited": "已退出",
}
_HIDDEN_TERMINAL_STATUSES = {"idle", "completed", "stopped", "exited"}


@dataclass(frozen=True, slots=True)
class ProgressItem:
    """One progress-bar row; ``None`` means indeterminate progress."""

    key: str
    label: str
    status: str
    detail: str
    value: float | None
    value_text: str | None = None


def task_progress_items(
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[ProgressItem, ...]:
    """Build a main row followed only by currently relevant feature rows."""
    moment = local_naive(now or datetime.now())
    main = resolve_main_progress(task, state, moment)
    items = [_overall_item(task, state, main)]
    status = str(state.get("status", "idle"))
    if status in _HIDDEN_TERMINAL_STATUSES:
        return tuple(items)
    records = progress_records(state)
    if status == "failed":
        selected = _failed_records(task, records)
    elif task.get("preset") == "eternal":
        selected = _eternal_records(records)
    elif main.stage == "waiting_capture":
        selected = ()
    elif main.stage in {"capture", "waiting_processing"}:
        selected = _finite_processing_records(records)
    else:
        selected = _unfinished_sunset_records(records)
    items.extend(_subtask_item(record) for record in selected)
    return tuple(items)


def _overall_item(
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    main: MainProgress,
) -> ProgressItem:
    status = str(state.get("status", "idle"))
    label = "持续拍摄" if task.get("preset") == "eternal" else "总体进度"
    if status == "completed":
        value, detail, value_text = 1.0, "已完成", None
    elif status in _TERMINAL_DETAILS:
        value, detail, value_text = 0.0, _TERMINAL_DETAILS[status], None
    else:
        value, detail, value_text = main.value, main.label, main.value_text
    return ProgressItem("overall", label, status, detail, value, value_text)


def _subtask_item(record: Mapping[str, Any]) -> ProgressItem:
    role = str(record.get("role") or record.get("name") or "")
    stage = record_stage(record)
    status = str(record.get("status") or "running")
    counts = progress_counts(record)
    value = progress_value(record)
    if status == "completed":
        value, detail = 1.0, "已完成"
    elif status == "failed":
        value, detail = value if value is not None else 0.0, "失败"
    elif status in {"stopped", "exited"}:
        value, detail = value if value is not None else 0.0, "已停止"
    elif value is not None and value >= 1:
        detail = "已追平"
    else:
        detail = "处理中"
    if role.startswith("bracketlapse-batch-"):
        sequence = role.rsplit("-", 1)[-1]
        key, label = f"subtask-batch-{sequence}", f"批次 {sequence}"
    elif role.startswith("sunsetscore"):
        key, label = "subtask-sunset", "晚霞评分"
    else:
        key, label = "subtask-hdr", "HDR处理"
    value_text = None
    if stage != "video" and counts is not None and counts[1] > 0:
        value_text = f"{counts[0]}/{counts[1]}"
    return ProgressItem(key, label, status, detail, value, value_text)


def _finite_processing_records(
    records: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    selected = []
    bracket = _latest(records, lambda record: _finite_bracket(record))
    sunset = _latest(records, _sunset)
    if bracket is not None and record_stage(bracket) == "hdr":
        selected.append(bracket)
    if sunset is not None:
        selected.append(sunset)
    return tuple(selected)


def _unfinished_sunset_records(
    records: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    sunset = _latest(records, _sunset)
    return (
        (sunset,) if sunset is not None and sunset.get("status") != "completed" else ()
    )


def _eternal_records(
    records: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    batch = _latest(
        records,
        lambda record: (
            str(record.get("role", "")).startswith("bracketlapse-batch-")
            and record.get("status") == "running"
        ),
    )
    sunset = _latest(
        records, lambda record: _sunset(record) and record.get("status") != "completed"
    )
    return tuple(record for record in (batch, sunset) if record is not None)


def _failed_records(
    task: Mapping[str, Any],
    records: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    bracket_test = (
        _eternal_batch if task.get("preset") == "eternal" else _finite_bracket
    )
    latest = (_latest(records, bracket_test), _latest(records, _sunset))
    return tuple(
        record
        for record in latest
        if record is not None and record.get("status") == "failed"
    )


def _latest(
    records: tuple[Mapping[str, Any], ...],
    predicate: Callable[[Mapping[str, Any]], bool],
) -> Mapping[str, Any] | None:
    return next((record for record in reversed(records) if predicate(record)), None)


def _finite_bracket(record: Mapping[str, Any]) -> bool:
    role = str(record.get("role", ""))
    return is_bracket_role(role) and not role.startswith("bracketlapse-batch-")


def _eternal_batch(record: Mapping[str, Any]) -> bool:
    return str(record.get("role", "")).startswith("bracketlapse-batch-")


def _sunset(record: Mapping[str, Any]) -> bool:
    return str(record.get("role", "")).startswith("sunsetscore")
