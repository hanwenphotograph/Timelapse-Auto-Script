"""Cleanup and label one successfully processed eternal batch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from timelapse_manager.album_naming import (
    label_sunset_album,
    rewrite_eternal_album_paths,
)
from timelapse_manager.errors import TaskError
from timelapse_manager.maintenance import check_disk_space, cleanup_work_directory
from timelapse_manager.runtime import TaskRuntime


class EternalBatchFinisher:
    def __init__(
        self,
        runtime: TaskRuntime,
        state_dir: Path,
        capture_dir: Path,
        album_lock: Any,
    ) -> None:
        self.runtime = runtime
        self.state_dir = state_dir
        self.capture_dir = capture_dir
        self.album_lock = album_lock

    def finish(
        self,
        sequence: int,
        batch_dir: Path,
        score_decision: Any,
    ) -> Path | None:
        if not self._cleanup(sequence, batch_dir, score_decision):
            return None
        self._check_disk(batch_dir)
        return self._label_album(sequence, batch_dir, score_decision)

    def _cleanup(self, sequence: int, batch_dir: Path, score_decision: Any) -> bool:
        cleanup = self.runtime.task["cleanup"]
        if not cleanup.get("enabled"):
            return True
        try:
            keep_directories = list(cleanup["keep_directories"])
            if (
                score_decision not in (None, False)
                and score_decision.retained_hdr
                and "hdr_enfuse" not in keep_directories
            ):
                keep_directories.append("hdr_enfuse")
            cleanup_work_directory(
                batch_dir,
                keep_directories,
                self.runtime.log,
                protected_paths=[
                    self.runtime.paths.root,
                    self.runtime.auto_root,
                    self.state_dir,
                    self.capture_dir,
                ],
            )
        except (OSError, TaskError) as exc:
            self.runtime.log(f"永续批次 {sequence} 清理失败: {exc}")
            return False
        return True

    def _check_disk(self, batch_dir: Path) -> None:
        threshold = float(self.runtime.project["disk_space_warning_threshold_gb"])
        remaining = check_disk_space(batch_dir, threshold, self.runtime.log)
        if threshold > 0 and remaining < threshold:
            self.runtime.notify_async(
                "disk_space_warning",
                f"磁盘剩余 {remaining:.2f}GB，低于阈值 {threshold:g}GB",
            )

    def _label_album(
        self,
        sequence: int,
        batch_dir: Path,
        score_decision: Any,
    ) -> Path:
        if score_decision in (None, False) or not score_decision.result.has_sunset:
            return batch_dir
        score = int(score_decision.result.max_score)
        try:
            with self.album_lock:
                renamed = label_sunset_album(
                    batch_dir,
                    self.runtime.auto_root,
                    score,
                )
                if renamed is None:
                    self.runtime.log(
                        f"永续批次 {sequence} 不在受管日期/时间相册结构内，跳过晚霞目录标记"
                    )
                    return batch_dir
                updated = rewrite_eternal_album_paths(
                    self.state_dir,
                    self.state_dir / "queue",
                    renamed.old_date_dir,
                    renamed.date_dir,
                )
        except (OSError, TaskError, ValueError) as exc:
            self.runtime.log(f"永续批次 {sequence} 晚霞相册标记失败: {exc}")
            raise TaskError(f"无法标记永续批次 {sequence} 的晚霞相册") from exc
        self.runtime.set_progress(
            eternal_last_album=str(renamed.work_dir),
            eternal_last_sunset_score=score,
        )
        self.runtime.log(
            f"永续批次 {sequence} 晚霞相册已标记为 S{score}：{renamed.work_dir}；"
            f"同步更新待处理路径 {updated} 个"
        )
        return renamed.work_dir
