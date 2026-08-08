"""Resolve persisted and legacy task state into one main progress stage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from timelapse_manager.progress_stages import MAIN_STAGES
from timelapse_manager.ui.progress_values import (
    capture_bounds,
    progress_counts,
    schedule_ratio,
)


STAGE_LABELS = {
    "waiting_capture": "等待拍摄",
    "capture": "相机拍摄",
    "waiting_processing": "等待处理",
    "video_processing": "视频处理",
    "eternal": "持续拍摄",
}


@dataclass(frozen=True, slots=True)
class MainProgress:
    stage: str
    label: str
    value: float | None
    value_text: str | None = None


def resolve_main_progress(
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    now: datetime,
) -> MainProgress:
    if task.get("preset") == "eternal":
        return MainProgress("eternal", STAGE_LABELS["eternal"], None, "持续运行")
    stage = infer_main_stage(task, state, now)
    if stage == "waiting_capture":
        bounds = capture_bounds(task)
        remaining = bounds[0] - now if bounds is not None and now < bounds[0] else None
        return MainProgress(
            stage,
            STAGE_LABELS[stage],
            0.0,
            f"距开始 {_duration_label(remaining)}" if remaining is not None else None,
        )
    if stage == "capture":
        bounds = capture_bounds(task)
        value = schedule_ratio(*bounds, now) if bounds is not None else None
        return MainProgress(stage, STAGE_LABELS[stage], value)
    if stage == "waiting_processing":
        value = _waiting_processing_value(progress_records(state))
        return MainProgress(
            stage,
            STAGE_LABELS[stage],
            value,
            "处理中" if value is None else None,
        )
    value = _video_processing_value(progress_records(state))
    return MainProgress(
        stage,
        STAGE_LABELS[stage],
        value,
        "处理中" if value is None else None,
    )


def infer_main_stage(
    task: Mapping[str, Any],
    state: Mapping[str, Any],
    now: datetime,
) -> str:
    progress = state.get("progress")
    if isinstance(progress, Mapping) and progress.get("main_stage") in MAIN_STAGES:
        return str(progress["main_stage"])
    records = progress_records(state)
    phase = str(state.get("phase") or "")
    if "视频" in phase or any(record_stage(record) == "video" for record in records):
        return "video_processing"
    camera_running = any(
        str(record.get("role", "")).startswith("camera-timelapse")
        and record.get("status") == "running"
        for record in records
    )
    bounds = capture_bounds(task)
    if camera_running:
        if bounds is not None and now < bounds[0] and "正在拍摄" not in phase:
            return "waiting_capture"
        return "capture"
    if bounds is not None and now < bounds[0]:
        return "waiting_capture"
    if any(
        _is_bracket_role(str(record.get("role", "")))
        and record.get("status") in {"running", "completed"}
        for record in records
    ) or any(record_stage(record) in {"hdr", "sunset"} for record in records):
        return "waiting_processing"
    if bounds is not None and now < bounds[1]:
        return "capture"
    if any(word in phase for word in ("HDR", "去闪", "后期", "晚霞")):
        return "waiting_processing"
    return "waiting_capture"


def progress_records(state: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    progress = state.get("progress")
    nested = progress if isinstance(progress, Mapping) else {}
    records: list[Mapping[str, Any]] = []
    for source in ("children", "threads", "subtasks"):
        value = state.get(source) or nested.get(source)
        if isinstance(value, Mapping):
            records.extend(
                {**record, "name": record.get("name") or str(name)}
                for name, record in value.items()
                if isinstance(record, Mapping)
            )
        elif isinstance(value, (list, tuple)):
            records.extend(record for record in value if isinstance(record, Mapping))
    return tuple(records)


def record_stage(record: Mapping[str, Any]) -> str | None:
    progress = record.get("progress")
    if isinstance(progress, Mapping) and progress.get("stage") in {
        "hdr",
        "sunset",
        "video",
    }:
        return str(progress["stage"])
    role = str(record.get("role") or record.get("name") or "")
    phase = str(record.get("phase") or "")
    if role.startswith("sunsetscore"):
        return "sunset"
    if _is_bracket_role(role):
        return "video" if "视频" in phase else "hdr"
    return None


def is_bracket_role(role: str) -> bool:
    return _is_bracket_role(role)


def _waiting_processing_value(records: tuple[Mapping[str, Any], ...]) -> float | None:
    tracked = []
    for stage in ("hdr", "sunset"):
        record = _latest_stage_record(records, stage)
        counts = progress_counts(record) if record is not None else None
        if counts is not None and counts[1] > 0:
            tracked.append((counts[0] / counts[1], record))
    if not tracked:
        return None
    if all(value >= 1 for value, _record in tracked) and any(
        record.get("status") == "running" for _value, record in tracked
    ):
        return None
    return sum(value for value, _record in tracked) / len(tracked)


def _video_processing_value(records: tuple[Mapping[str, Any], ...]) -> float | None:
    candidates = [record for record in records if record_stage(record) == "video"]
    if not candidates:
        return None
    record = candidates[-1]
    counts = progress_counts(record)
    if counts is not None and counts[1] > 0:
        return counts[0] / counts[1]
    return 1.0 if record.get("status") == "completed" else None


def _latest_stage_record(
    records: tuple[Mapping[str, Any], ...],
    stage: str,
) -> Mapping[str, Any] | None:
    matches = [record for record in records if record_stage(record) == stage]
    running = [record for record in matches if record.get("status") == "running"]
    return (running or matches or [None])[-1]


def _is_bracket_role(role: str) -> bool:
    return role in {"bracketlapse-standby", "bracketlapse-process"} or role.startswith(
        "bracketlapse-batch-"
    )


def _duration_label(value: timedelta) -> str:
    minutes = max(0, int(value.total_seconds() // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}小时{minutes:02d}分" if hours else f"{minutes}分"
