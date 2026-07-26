"""Output cleanup and disk-space checks."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from timelapse_manager.errors import TaskError


LogCallback = Callable[[str], None]


def cleanup_work_directory(
    directory: Path,
    keep: list[str],
    log: LogCallback,
    *,
    protected_paths: list[Path] | None = None,
) -> None:
    target = directory.expanduser().resolve()
    anchor = Path(target.anchor).resolve()
    protected = {Path.home().resolve()}
    protected.update(path.expanduser().resolve() for path in (protected_paths or []))
    if target == anchor or len(target.parts) < 3 or target in protected:
        raise TaskError(f"拒绝清理不安全的目录: {target}")
    if not target.is_dir():
        raise TaskError(f"清理目录不存在: {target}")
    keep_set = set(keep)
    log(f"清理工作目录，仅保留: {', '.join(sorted(keep_set)) or '无'}")
    for entry in target.iterdir():
        if entry.name in keep_set:
            log(f"保留: {entry}")
            continue
        log(f"删除: {entry}")
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink(missing_ok=True)


def disk_free_gb(directory: Path) -> float:
    return shutil.disk_usage(directory).free / 1024 / 1024 / 1024


def check_disk_space(directory: Path, threshold_gb: float, log: LogCallback) -> float:
    remaining = disk_free_gb(directory)
    if threshold_gb > 0 and remaining < threshold_gb:
        log(f"警告: 磁盘剩余 {remaining:.2f}GB，低于阈值 {threshold_gb:g}GB")
    return remaining
