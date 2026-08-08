"""Recover display-only child progress from logs written by older workers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import threading
from typing import Any

from timelapse_manager.child_progress import update_child_progress
from timelapse_manager.sunset_score.jsonl_protocol import scan_progress


_ACTIVE_STATUSES = {"starting", "running", "stopping", "finishing"}
_CAPTURE_ROUND = re.compile(
    r"\[camera-timelapse(?:-eternal)?\].*Starting\s+capture\s+round\s+(\d+)"
)
_HDR_EVENT_PREFIX = "BRACKETLAPSE_EVENT "
_RUN_STARTED = "任务工作进程启动，模式="
_SUNSET_MARKER = "[sunsetscore-resident] "


@dataclass(frozen=True, slots=True)
class RecoveredProgress:
    hdr_completed: int = 0
    hdr_total: int = 0
    sunset_completed: int = 0
    sunset_total: int = 0


@dataclass(slots=True)
class _LogEntry:
    session_key: str
    file_identity: tuple[int, int] | None = None
    offset: int = 0
    pending: bytes = b""
    hdr_completed: int = 0
    hdr_total: int = 0
    sunset_sessions: dict[str, tuple[int, int]] = field(default_factory=dict)

    def clear_file(self) -> None:
        self.file_identity = None
        self.offset = 0
        self.pending = b""
        self.clear_counts()

    def clear_counts(self) -> None:
        self.hdr_completed = 0
        self.hdr_total = 0
        self.sunset_sessions.clear()

    def snapshot(self) -> RecoveredProgress:
        return RecoveredProgress(
            self.hdr_completed,
            self.hdr_total,
            sum(value[0] for value in self.sunset_sessions.values()),
            sum(value[1] for value in self.sunset_sessions.values()),
        )


class TaskLogProgressReader:
    """Incrementally parse task logs and enrich an in-memory state copy."""

    def __init__(self) -> None:
        self._entries: dict[Path, _LogEntry] = {}
        self._lock = threading.Lock()

    def enrich_state(
        self,
        state: Mapping[str, Any],
        log_path: Path,
    ) -> dict[str, Any]:
        result = dict(state)
        children_value = state.get("children")
        if (
            state.get("status") not in _ACTIVE_STATUSES
            or not isinstance(children_value, Sequence)
            or isinstance(children_value, (str, bytes))
        ):
            return result
        children = [dict(item) for item in children_value if isinstance(item, Mapping)]
        roles = {
            str(item.get("role"))
            for item in children
            if item.get("status") == "running"
        }
        supported = roles & {
            "bracketlapse-standby",
            "bracketlapse-process",
            "sunsetscore-resident",
        }
        if not supported:
            result["children"] = children
            return result

        session_key = f"{state.get('started_at')}:{state.get('runner_pid')}"
        recovered = self.read(log_path, session_key)
        for role in supported & {"bracketlapse-standby", "bracketlapse-process"}:
            if recovered.hdr_total > 0:
                children, _changed = update_child_progress(
                    children,
                    role,
                    completed=recovered.hdr_completed,
                    total=recovered.hdr_total,
                    phase="HDR处理",
                )
        if "sunsetscore-resident" in supported and recovered.sunset_total > 0:
            children, _changed = update_child_progress(
                children,
                "sunsetscore-resident",
                completed=recovered.sunset_completed,
                total=recovered.sunset_total,
                phase="晚霞评分",
            )
        result["children"] = children
        return result

    def read(self, path: Path, session_key: str) -> RecoveredProgress:
        resolved = path.resolve()
        with self._lock:
            entry = self._entries.get(resolved)
            if entry is None or entry.session_key != session_key:
                entry = _LogEntry(session_key)
                self._entries[resolved] = entry
            try:
                stat = resolved.stat()
            except OSError:
                return entry.snapshot()
            identity = (stat.st_dev, stat.st_ino)
            if (
                entry.file_identity not in (None, identity)
                or stat.st_size < entry.offset
            ):
                entry.clear_file()
            entry.file_identity = identity
            try:
                with resolved.open("rb") as handle:
                    handle.seek(entry.offset)
                    appended = handle.read()
                    entry.offset = handle.tell()
            except OSError:
                return entry.snapshot()
            lines = (entry.pending + appended).split(b"\n")
            entry.pending = lines.pop()
            for raw_line in lines:
                self._parse_line(entry, raw_line.decode("utf-8", errors="replace"))
            return entry.snapshot()

    @staticmethod
    def _parse_line(entry: _LogEntry, line: str) -> None:
        if _RUN_STARTED in line:
            entry.clear_counts()
        match = _CAPTURE_ROUND.search(line)
        if match:
            entry.hdr_total = max(entry.hdr_total, int(match.group(1)))

        document = _document_after(line, _HDR_EVENT_PREFIX)
        if document is not None and document.get("event") == "hdr_ready":
            frame = document.get("frame_number")
            if type(frame) is int and frame > 0:
                entry.hdr_completed = max(entry.hdr_completed, frame)
                entry.hdr_total = max(entry.hdr_total, entry.hdr_completed)

        document = _document_after(line, _SUNSET_MARKER)
        if document is None:
            return
        counts = scan_progress(document)
        if counts is None:
            return
        session = document.get("session")
        key = str(session) if session is not None else ""
        previous = entry.sunset_sessions.get(key, (0, 0))
        completed = max(previous[0], counts[0])
        total = max(previous[1], counts[1], completed)
        entry.sunset_sessions[key] = (completed, total)


def _document_after(line: str, marker: str) -> dict[str, Any] | None:
    index = line.find(marker)
    if index < 0:
        return None
    payload = line[index + len(marker) :].lstrip()
    try:
        value, _end = json.JSONDecoder().raw_decode(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None
