"""Display-only video progress recovered from managed task logs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from timelapse_manager.child_progress import update_child_progress


_BRACKET_ROLE = re.compile(r"\[(bracketlapse-(?:standby|process|batch-\d+))\]")
_VIDEO_EVENTS = {"video_started", "video_progress", "video_completed"}


@dataclass(frozen=True, slots=True)
class RecoveredVideoProgress:
    started: bool = False
    completed: int = 0
    total: int = 0
    role: str = ""


@dataclass(slots=True)
class VideoLogProgress:
    started: bool = False
    completed: int = 0
    total: int = 0
    role: str = ""

    def clear(self) -> None:
        self.started = False
        self.completed = 0
        self.total = 0
        self.role = ""

    def snapshot(self) -> RecoveredVideoProgress:
        return RecoveredVideoProgress(
            self.started,
            self.completed,
            self.total,
            self.role,
        )

    def consume(self, line: str, document: Mapping[str, Any] | None) -> None:
        event = document.get("event") if document is not None else None
        if not isinstance(event, str) or event not in _VIDEO_EVENTS:
            if "Creating video from " in line:
                role = bracket_role(line)
                if role:
                    self._start(role, 0)
            return
        completed = document.get("completed")
        total = document.get("total")
        if (
            type(completed) is not int
            or type(total) is not int
            or completed < 0
            or total <= 0
            or completed > total
        ):
            return
        role = bracket_role(line) or self.role
        if not role:
            return
        if event == "video_started" or role != self.role:
            self._start(role, total)
        self.started = True
        self.completed = max(self.completed, completed)
        self.total = max(self.total, total, self.completed)

    def _start(self, role: str, total: int) -> None:
        self.started = True
        self.completed = 0
        self.total = total
        self.role = role


def enrich_video_state(
    result: dict[str, Any],
    children: list[dict[str, Any]],
    recovered: RecoveredVideoProgress,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    bracket_roles = {
        str(item.get("role"))
        for item in children
        if is_bracket_role(str(item.get("role")))
    }
    if not recovered.started or not bracket_roles:
        return result, children
    role = (
        recovered.role
        if recovered.role in bracket_roles
        else latest_bracket_role(children)
    )
    if role:
        children, _changed = update_child_progress(
            children,
            role,
            completed=recovered.completed,
            total=recovered.total,
            stage="video",
            phase="视频处理",
            running_only=False,
        )
    value = result.get("progress")
    progress = dict(value) if isinstance(value, Mapping) else {}
    progress["main_stage"] = "video_processing"
    result["progress"] = progress
    return result, children


def bracket_role(line: str) -> str:
    match = _BRACKET_ROLE.search(line)
    return match.group(1) if match else ""


def is_bracket_role(role: str) -> bool:
    return role in {"bracketlapse-standby", "bracketlapse-process"} or role.startswith(
        "bracketlapse-batch-"
    )


def latest_bracket_role(children: Sequence[Mapping[str, Any]]) -> str:
    for child in reversed(children):
        role = str(child.get("role"))
        if is_bracket_role(role):
            return role
    return ""
