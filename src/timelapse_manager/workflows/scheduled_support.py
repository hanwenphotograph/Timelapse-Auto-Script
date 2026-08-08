"""Event handlers and finalization for finite capture workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from timelapse_manager.bracketlapse import parse_hdr_ready
from timelapse_manager.errors import TaskError
from timelapse_manager.maintenance import check_disk_space, cleanup_work_directory

if TYPE_CHECKING:
    from timelapse_manager.runtime import TaskRuntime


@dataclass(frozen=True)
class WorkSpec:
    label: str
    work_dir: Path
    start_date: str
    start_at: str
    end_date: str
    end_at: str

    @property
    def score_label(self) -> str:
        return (
            f"{self.label}延时摄影，日期 {self.start_date}，"
            f"时间 {self.start_at}-{self.end_at}"
        )


def camera_output_handler(
    runtime: TaskRuntime, spec: WorkSpec
) -> Callable[[str], None]:
    capture_started = False
    capture_ended = False

    def handle(line: str) -> None:
        nonlocal capture_started, capture_ended
        if "Starting capture round " in line and not capture_started:
            capture_started = True
            runtime.set_phase("正在拍摄", f"{spec.label}任务已进入实际拍摄阶段")
            runtime.notify_async(
                "entered_key_node",
                f"camera-timelapse 真正开始拍摄，日期 {spec.start_date}，目录 {spec.work_dir}",
            )
        if (
            "Scheduled end time " in line
            and "reached; stopping after this round" in line
            and capture_started
            and not capture_ended
        ):
            capture_ended = True
            runtime.set_phase("拍摄即将结束", "已到达计划结束时间")
            runtime.notify_async(
                "exited_key_node",
                f"camera-timelapse 已按计划结束，目录 {spec.work_dir}",
            )

    return handle


def bracket_output_handler(
    runtime: TaskRuntime,
    spec: WorkSpec,
    on_hdr_ready: Callable[[], None] | None = None,
) -> Callable[[str], None]:
    enfuse_started = False
    deflick_started = False

    def handle(line: str) -> None:
        nonlocal enfuse_started, deflick_started
        event = parse_hdr_ready(line, spec.work_dir)
        if event is not None and on_hdr_ready is not None:
            on_hdr_ready()
        if "Fusing " in line and not enfuse_started:
            enfuse_started = True
            runtime.set_phase("HDR 融合", str(spec.work_dir))
            runtime.notify_async(
                "entered_key_node", f"enfuse 开始融合，目录 {spec.work_dir}"
            )
        if "Deflickering fused frames." in line and not deflick_started:
            deflick_started = True
            runtime.set_phase("去闪处理", str(spec.work_dir))
            runtime.notify_async(
                "entered_key_node",
                f"simple-deflicker 开始去闪，目录 {spec.work_dir}",
            )
        if "Creating video from " in line or line.rstrip().endswith("Done."):
            runtime.set_phase("视频导出", str(spec.work_dir))

    return handle


class ScheduledFinisher:
    def __init__(self, runtime: TaskRuntime):
        self.runtime = runtime
        self.task = runtime.task
        self.project = runtime.project

    def finish(self, spec: WorkSpec, success: bool, score_session=None) -> bool:
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

        cleanup = self.task["cleanup"]
        if cleanup.get("enabled") and (success or cleanup.get("on_failure")):
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
                )
            except (OSError, TaskError) as exc:
                self.runtime.log(f"清理工作目录失败: {exc}")
                success = False
        self._check_disk(spec)
        if success and score_decision is None and not score_attempted:
            self.runtime.webhook.notify_image(
                "webhook-image", f"图片推送：{spec.score_label}", spec.work_dir
            )
        self.runtime.notify_async(
            "ended",
            f"任务{'完成' if success else '失败'}：{spec.label}，目录 {spec.work_dir}",
        )
        return success

    def _check_disk(self, spec: WorkSpec) -> None:
        threshold = float(self.project["disk_space_warning_threshold_gb"])
        remaining = check_disk_space(spec.work_dir, threshold, self.runtime.log)
        if threshold > 0 and remaining < threshold:
            self.runtime.notify_async(
                "disk_space_warning",
                f"磁盘剩余 {remaining:.2f}GB，低于阈值 {threshold:g}GB",
            )
