"""Persisted progress updates for managed child processes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def update_child_progress(
    records: Sequence[Mapping[str, Any]],
    role: str,
    *,
    completed: int | None = None,
    total: int | None = None,
    phase: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Update the newest running child with monotonic completed/total counts."""
    _validate_count(completed, "completed")
    _validate_count(total, "total")
    children = [dict(record) for record in records]
    for record in reversed(children):
        if record.get("role") != role or record.get("status") != "running":
            continue
        current = record.get("progress")
        progress = dict(current) if isinstance(current, Mapping) else {}
        previous_completed = _stored_count(progress.get("completed"))
        previous_total = _stored_count(progress.get("total"))
        next_completed = max(previous_completed, completed or 0)
        next_total = max(previous_total, total or 0, next_completed)
        changed = (next_completed, next_total) != (
            previous_completed,
            previous_total,
        )
        if changed:
            record["progress"] = {
                "completed": next_completed,
                "total": next_total,
            }
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
