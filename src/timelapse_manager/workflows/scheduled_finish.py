"""Finalize one finite capture and label its managed album."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from timelapse_manager.album_naming import label_sunset_album
from timelapse_manager.errors import TaskError
from timelapse_manager.maintenance import check_disk_space, cleanup_work_directory
from timelapse_manager.runtime import TaskRuntime
from timelapse_manager.workflows.scheduled_support import WorkSpec


class ScheduledFinisher:
    def __init__(self, runtime: TaskRuntime):
        self.runtime = runtime
        self.task = runtime.task
        self.project = runtime.project

    def finish(
        self,
        spec: WorkSpec,
        success: bool,
        score_session: Any = None,
        *,
        capture_started: bool = True,
        preserve_names: frozenset[str] = frozenset(),
    ) -> bool:
        score_decision = None
        score_attempted = False
        protect_hdr = False
        if success and self.task["processing"].get("enabled", True):
            score_attempted = self.runtime.sunset_score.enabled
            protect_hdr = score_attempted
            try:
                score_decision = (
                    score_session.finish()
                    if score_session is not None
                    else self.runtime.sunset_score.process(
                        spec.work_dir, spec.score_label
                    )
                )
            except TaskError as exc:
                self.runtime.log(f"{spec.label}延时摄影晚霞评分失败: {exc}")
                success = False
            else:
                if score_decision is not None:
                    protect_hdr = score_decision.retained_hdr

        if not self._cleanup(
            spec,
            success,
            capture_started,
            protect_hdr,
            preserve_names,
        ):
            success = False
        self._check_disk(spec.work_dir)
        if success and score_decision is None and not score_attempted:
            self.runtime.webhook.notify_image(
                "webhook-image", f"图片推送：{spec.score_label}", spec.work_dir
            )
        final_dir = spec.work_dir
        if success:
            try:
                final_dir = self._label_album(spec.work_dir, score_decision)
            except (OSError, TaskError, ValueError) as exc:
                self.runtime.log(f"晚霞相册标记失败: {exc}")
                success = False
        self.runtime.notify_async(
            "ended",
            f"任务{'完成' if success else '失败'}：{spec.label}，目录 {final_dir}",
        )
        return success

    def _cleanup(
        self,
        spec: WorkSpec,
        success: bool,
        capture_started: bool,
        protect_hdr: bool,
        preserve_names: frozenset[str],
    ) -> bool:
        cleanup = self.task["cleanup"]
        requested = cleanup.get("enabled") and (success or cleanup.get("on_failure"))
        if requested and not success and not capture_started:
            self.runtime.log("拍摄尚未开始，跳过失败清理以保护工作目录")
            return True
        if not requested:
            return True
        try:
            keep_directories = list(cleanup["keep_directories"])
            if protect_hdr and "hdr_enfuse" not in keep_directories:
                keep_directories.append("hdr_enfuse")
            cleanup_work_directory(
                spec.work_dir,
                keep_directories,
                self.runtime.log,
                protected_paths=[
                    self.runtime.paths.root,
                    self.runtime.auto_root,
                ],
                preserve_names=preserve_names,
            )
        except (OSError, TaskError) as exc:
            self.runtime.log(f"清理工作目录失败: {exc}")
            return False
        return True

    def _check_disk(self, work_dir: Path) -> None:
        threshold = float(self.project["disk_space_warning_threshold_gb"])
        remaining = check_disk_space(work_dir, threshold, self.runtime.log)
        if threshold > 0 and remaining < threshold:
            self.runtime.notify_async(
                "disk_space_warning",
                f"磁盘剩余 {remaining:.2f}GB，低于阈值 {threshold:g}GB",
            )

    def _label_album(self, work_dir: Path, score_decision: Any) -> Path:
        if score_decision is None or not score_decision.result.has_sunset:
            return work_dir
        score = int(score_decision.result.max_score)
        renamed = label_sunset_album(work_dir, self.runtime.auto_root, score)
        if renamed is None:
            self.runtime.log("任务目录不在受管日期/时间相册结构内，跳过晚霞目录标记")
            return work_dir
        self.runtime.set_progress(
            album_path=str(renamed.work_dir),
            sunset_score=score,
        )
        self.runtime.log(f"晚霞相册已标记为 S{score}：{renamed.work_dir}")
        return renamed.work_dir
