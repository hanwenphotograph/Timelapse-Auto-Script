"""Output cleanup and disk-space checks."""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from timelapse_manager.errors import TaskError


LogCallback = Callable[[str], None]
HDR_DELETION_MARKER = ".timelapse-hdr-enfuse-delete"
HDR_DELETION_DELAY = timedelta(days=3)


def mark_hdr_for_deletion(
    hdr_dir: Path,
    *,
    now: datetime | None = None,
) -> Path:
    """Record a delayed deletion deadline inside an HDR directory."""
    target = hdr_dir.expanduser().resolve()
    if target.name != "hdr_enfuse" or not target.is_dir() or hdr_dir.is_symlink():
        raise TaskError(f"HDR 目录不存在或不安全: {hdr_dir}")
    deadline = (now or datetime.now(timezone.utc)) + HDR_DELETION_DELAY
    marker = target / HDR_DELETION_MARKER
    marker.write_text(deadline.isoformat(timespec="seconds") + "\n", encoding="utf-8")
    return marker


def has_hdr_deletion_marker(hdr_dir: Path) -> bool:
    marker = hdr_dir / HDR_DELETION_MARKER
    return marker.is_file() and not marker.is_symlink()


def process_deferred_hdr_deletions(
    root: Path,
    log: LogCallback,
    *,
    now: datetime | None = None,
) -> int:
    """Delete only due ``hdr_enfuse`` directories carrying our marker."""
    target_root = root.expanduser().resolve()
    if not target_root.is_dir():
        return 0
    current = now or datetime.now(timezone.utc)
    deleted = 0
    markers = list(target_root.rglob(HDR_DELETION_MARKER))
    for marker in markers:
        if marker.is_symlink() or marker.parent.name != "hdr_enfuse":
            continue
        hdr_dir = marker.parent
        try:
            hdr_dir.resolve().relative_to(target_root)
            deadline = _read_deletion_deadline(marker)
        except (OSError, ValueError) as exc:
            log(f"跳过无效 HDR 延迟删除标记 {marker}: {exc}")
            continue
        if current < deadline:
            continue
        try:
            shutil.rmtree(hdr_dir)
        except OSError as exc:
            log(f"延迟删除 HDR 目录失败 {hdr_dir}: {exc}")
            continue
        log(f"已执行三日延迟删除，移除 HDR 照片目录：{hdr_dir}")
        deleted += 1
    return deleted


def _read_deletion_deadline(marker: Path) -> datetime:
    value = marker.read_text(encoding="utf-8").strip()
    deadline = datetime.fromisoformat(value)
    if deadline.tzinfo is None:
        raise ValueError("删除截止时间缺少时区")
    return deadline.astimezone(timezone.utc)


def cleanup_work_directory(
    directory: Path,
    keep: list[str],
    log: LogCallback,
    *,
    protected_paths: list[Path] | None = None,
    preserve_names: set[str] | frozenset[str] | None = None,
) -> None:
    target = directory.expanduser().resolve()
    anchor = Path(target.anchor).resolve()
    protected = {Path.home().resolve()}
    protected.update(path.expanduser().resolve() for path in (protected_paths or []))
    if target == anchor or len(target.parts) < 3 or target in protected:
        raise TaskError(f"拒绝清理不安全的目录: {target}")
    if not target.is_dir():
        raise TaskError(f"清理目录不存在: {target}")
    keep_set = set(keep) | set(preserve_names or ())
    log(f"清理工作目录，仅保留: {', '.join(sorted(keep_set)) or '无'}")
    for entry in target.iterdir():
        if entry.name == "hdr_enfuse" and has_hdr_deletion_marker(entry):
            log(f"保留: {entry}（已标记为三日后删除）")
            continue
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
