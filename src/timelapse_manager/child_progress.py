"""Persisted progress updates for managed child processes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from timelapse_manager.progress_stages import validate_child_stage


def update_child_progress(
    records: Sequence[Mapping[str, Any]],
    role: str,
    *,
    completed: int | None = None,
    total: int | None = None,
    stage: str | None = None,
    phase: str | None = None,
    running_only: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    """Update one child monotonically until its progress stage changes."""
    _validate_count(completed, "completed")
    _validate_count(total, "total")
    validate_child_stage(stage)
    children = [dict(record) for record in records]
    for record in reversed(children):
        if record.get("role") != role or (
            running_only and record.get("status") != "running"
        ):
            continue
        current = record.get("progress")
        progress = dict(current) if isinstance(current, Mapping) else {}
        previous_stage = progress.get("stage")
        stage_changed = stage is not None and stage != previous_stage
        previous_completed = (
            0 if stage_changed else _stored_count(progress.get("completed"))
        )
        previous_total = 0 if stage_changed else _stored_count(progress.get("total"))
        next_completed = max(previous_completed, completed or 0)
        next_total = max(previous_total, total or 0, next_completed)
        next_stage = stage if stage is not None else previous_stage
        next_progress: dict[str, object] = {
            "completed": next_completed,
            "total": next_total,
        }
        if isinstance(next_stage, str):
            next_progress = {"stage": next_stage, **next_progress}
        changed = next_progress != progress
        if changed:
            record["progress"] = next_progress
        if phase and record.get("phase") != phase:
            record["phase"] = phase
            changed = True
        return children, changed
    return children, False


def _validate_count(value: int | None, name: str) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError(f"{name} 必须是非负整数")


def _stored_count(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0
