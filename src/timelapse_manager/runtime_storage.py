"""Check worker storage before state and media writes exhaust the volume."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from timelapse_manager.errors import TaskError
from timelapse_manager.maintenance import disk_free_gb


MINIMUM_FREE_GB = 1.0


class StorageGuard:
    def __init__(
        self,
        directories: list[Path],
        warning_gb: float,
        log: Callable[[str], None],
        notify: Callable[[str, str], None],
    ) -> None:
        self.directories = directories
        self.warning_gb = warning_gb
        self.log = log
        self.notify = notify
        self._next_check = 0.0
        self._warned: set[int] = set()

    def check(self) -> None:
        current = time.monotonic()
        if current < self._next_check:
            return
        self._next_check = current + 5
        checked: set[int] = set()
        for directory in self.directories:
            existing = directory
            while not existing.exists() and existing != existing.parent:
                existing = existing.parent
            device = existing.stat().st_dev
            if device in checked:
                continue
            checked.add(device)
            remaining = disk_free_gb(existing)
            if remaining < MINIMUM_FREE_GB:
                raise TaskError(
                    f"磁盘剩余 {remaining:.2f}GB，低于安全余量 {MINIMUM_FREE_GB:g}GB；"
                    f"停止拍摄和处理以保留原片，请释放空间后重启任务：{directory}"
                )
            if self.warning_gb > 0 and remaining < self.warning_gb:
                if device not in self._warned:
                    message = (
                        f"磁盘剩余 {remaining:.2f}GB，低于阈值 {self.warning_gb:g}GB："
                        f"{directory}"
                    )
                    self.log(message)
                    self.notify("disk_space_warning", message)
                    self._warned.add(device)
            else:
                self._warned.discard(device)
