"""Parse installer output into determinate progress values."""

from __future__ import annotations

import re
from collections.abc import Iterable


_START_DOWNLOAD = re.compile(r"开始下载\s+(.+?)（([\d.]+)\s*MB）")
_FILE_PERCENT = re.compile(r"(?:下载进度|继续下载)\s+(.+?)[，：].*?([\d.]+)\s*%")
_FINISHED_FILE = re.compile(r"(?:下载完成|正在校验)：\s*(.+?)\s*$")
_GENERIC_PERCENT = re.compile(r"([\d.]+)\s*%")


class InstallProgressTracker:
    def __init__(self, known_sizes: Iterable[tuple[str, int]] = ()) -> None:
        self._sizes = dict(known_sizes)
        self._fractions = {name: 0.0 for name in self._sizes}

    def consume(self, message: str) -> float | None:
        started = _START_DOWNLOAD.search(message)
        if started:
            name, megabytes = started.groups()
            self._sizes.setdefault(name, round(float(megabytes) * 1024**2))
            self._fractions.setdefault(name, 0.0)
            return self._weighted_progress()

        file_percent = _FILE_PERCENT.search(message)
        if file_percent:
            name, percent = file_percent.groups()
            if name in self._sizes:
                self._fractions[name] = _fraction(percent)
                return self._weighted_progress()

        finished = _FINISHED_FILE.search(message)
        if finished and finished.group(1) in self._sizes:
            self._fractions[finished.group(1)] = 1.0
            return self._weighted_progress()

        if self._sizes:
            return None
        percentages = _GENERIC_PERCENT.findall(message)
        return _fraction(percentages[-1]) if percentages else None

    def _weighted_progress(self) -> float:
        total = sum(self._sizes.values())
        if not total:
            return 0.0
        completed = sum(
            size * self._fractions.get(name, 0.0) for name, size in self._sizes.items()
        )
        return min(1.0, max(0.0, completed / total))


def _fraction(percent: str) -> float:
    return min(1.0, max(0.0, float(percent) / 100))
