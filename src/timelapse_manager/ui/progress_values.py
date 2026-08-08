"""Numeric progress parsing and scheduled-capture calculations."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from numbers import Real
from typing import Any


def overall_value(state: Mapping[str, Any]) -> float | None:
    progress = state.get("progress")
    if not isinstance(progress, Mapping):
        return None
    return progress_value(progress.get("overall"))


def progress_value(value: object) -> float | None:
    """Normalize common persisted progress shapes to a 0..1 value."""
    if isinstance(value, Mapping):
        for key in ("value", "ratio", "fraction", "progress"):
            result = _unit_value(value.get(key))
            if result is not None:
                return result
        nested = value.get("progress")
        if isinstance(nested, Mapping):
            result = progress_value(nested)
            if result is not None:
                return result
        percent = value.get("percent")
        if isinstance(percent, Real) and not isinstance(percent, bool):
            return _clamp(float(percent) / 100)
        counts = progress_counts(value)
        if counts is not None and counts[1] > 0:
            return _clamp(counts[0] / counts[1])
        return None
    return _unit_value(value)


def progress_counts(value: object) -> tuple[int, int] | None:
    """Extract exact completed/total counts from a progress mapping."""
    if not isinstance(value, Mapping):
        return None
    completed = value.get("completed")
    total = value.get("total")
    if all(type(item) is int and item >= 0 for item in (completed, total)):
        return (completed, total) if completed <= total else None
    nested = value.get("progress")
    return progress_counts(nested)


def capture_bounds(
    task: Mapping[str, Any],
) -> tuple[datetime, datetime] | None:
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


def active_schedule_value(
    bounds: tuple[datetime, datetime] | None,
    now: datetime,
) -> float | None:
    if bounds is None:
        return None
    start, end = bounds
    if now < start:
        return 0.0
    return schedule_ratio(start, end, now) if now < end else None


def schedule_ratio(start: datetime, end: datetime, now: datetime) -> float:
    return _clamp((now - start) / (end - start))


def local_naive(value: datetime) -> datetime:
    return value.astimezone().replace(tzinfo=None) if value.tzinfo else value


def _unit_value(value: object) -> float | None:
    if not _is_number(value):
        return None
    numeric = float(value)
    return _clamp(numeric / 100 if numeric > 1 else numeric)


def _is_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
