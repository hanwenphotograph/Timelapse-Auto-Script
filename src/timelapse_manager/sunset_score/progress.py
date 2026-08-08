"""Aggregate live progress for SunsetScore JSONL sessions."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

from timelapse_manager.sunset_score.jsonl_protocol import (
    format_scan_response,
    scan_progress,
)

if TYPE_CHECKING:
    from timelapse_manager.runtime import TaskRuntime


_SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png"}


class SunsetProgressTracker:
    def __init__(self, runtime: TaskRuntime, interval: int) -> None:
        self.runtime = runtime
        self.interval = interval
        self._lock = threading.Lock()
        self._sessions: dict[str, tuple[int, int]] = {}

    def submitted(self, session_id: str, directory: Path) -> None:
        total = _sampled_image_count(directory, self.interval)
        if total is not None:
            self._update(session_id, total=total)

    def response(self, session_id: str | None, value: dict[str, object]) -> None:
        message = format_scan_response(session_id, value)
        if message is not None:
            self.runtime.log(message)
        counts = scan_progress(value)
        if session_id is not None and counts is not None:
            self._update(session_id, completed=counts[0], total=counts[1])

    def _update(
        self,
        session_id: str,
        *,
        completed: int | None = None,
        total: int | None = None,
    ) -> None:
        with self._lock:
            current_completed, current_total = self._sessions.get(session_id, (0, 0))
            next_completed = max(current_completed, completed or 0)
            next_total = max(current_total, total or 0, next_completed)
            if (next_completed, next_total) == (current_completed, current_total):
                return
            self._sessions[session_id] = (next_completed, next_total)
            aggregate_completed = sum(item[0] for item in self._sessions.values())
            aggregate_total = sum(item[1] for item in self._sessions.values())
        self.runtime.set_child_progress(
            "sunsetscore-resident",
            completed=aggregate_completed,
            total=aggregate_total,
            stage="sunset",
            phase="晚霞评分",
        )


def _sampled_image_count(directory: Path, interval: int) -> int | None:
    try:
        image_count = sum(
            1
            for path in directory.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.casefold() in _SUPPORTED_SUFFIXES
        )
    except OSError:
        return None
    return (image_count + interval - 1) // interval
