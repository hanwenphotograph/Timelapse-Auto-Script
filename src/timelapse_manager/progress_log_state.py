"""Cached cursor and aggregate state for incremental task-log reads."""

from __future__ import annotations

from dataclasses import dataclass, field

from timelapse_manager.progress_video_compat import (
    RecoveredVideoProgress,
    VideoLogProgress,
)


@dataclass(frozen=True, slots=True)
class RecoveredProgress:
    hdr_completed: int = 0
    hdr_total: int = 0
    sunset_completed: int = 0
    sunset_total: int = 0
    video: RecoveredVideoProgress = RecoveredVideoProgress()


@dataclass(slots=True)
class LogProgressEntry:
    session_key: str
    file_identity: tuple[int, int] | None = None
    offset: int = 0
    pending: bytes = b""
    hdr_completed: int = 0
    hdr_total: int = 0
    sunset_sessions: dict[str, tuple[int, int]] = field(default_factory=dict)
    video: VideoLogProgress = field(default_factory=VideoLogProgress)

    def clear_file(self) -> None:
        self.file_identity = None
        self.offset = 0
        self.pending = b""
        self.clear_counts()

    def clear_counts(self) -> None:
        self.hdr_completed = 0
        self.hdr_total = 0
        self.sunset_sessions.clear()
        self.video.clear()

    def snapshot(self) -> RecoveredProgress:
        return RecoveredProgress(
            self.hdr_completed,
            self.hdr_total,
            sum(value[0] for value in self.sunset_sessions.values()),
            sum(value[1] for value in self.sunset_sessions.values()),
            self.video.snapshot(),
        )
