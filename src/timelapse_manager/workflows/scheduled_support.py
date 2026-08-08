"""Event handlers and finalization for finite capture workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, TYPE_CHECKING

from timelapse_manager.bracketlapse import parse_hdr_ready, parse_video_progress

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


@dataclass
class CaptureProgress:
    started: bool = False
    rounds: int = 0
    hdr_completed: int = 0


def camera_output_handler(
    runtime: TaskRuntime,
    spec: WorkSpec,
    progress: CaptureProgress | None = None,
    *,
    hdr_role: str | None = None,
) -> Callable[[str], None]:
    capture_started = False
    capture_ended = False
    capture_rounds = 0

    def handle(line: str) -> None:
        nonlocal capture_started, capture_ended, capture_rounds
        match = re.search(r"Starting\s+capture\s+round\s+(\d+)", line)
        if match:
            capture_rounds = max(capture_rounds, int(match.group(1)))
            if progress is not None:
                progress.rounds = capture_rounds
            if hdr_role is not None:
                runtime.set_child_progress(
                    hdr_role,
                    total=capture_rounds,
                    stage="hdr",
                    phase="HDR处理",
                )
            if not capture_started:
                capture_started = True
                if progress is not None:
                    progress.started = True
                runtime.set_main_stage("capture")
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
    *,
    progress: CaptureProgress | None = None,
    child_role: str = "bracketlapse-standby",
) -> Callable[[str], None]:
    enfuse_started = False
    deflick_started = False
    video_started = False

    def handle(line: str) -> None:
        nonlocal enfuse_started, deflick_started, video_started
        event = parse_hdr_ready(line, spec.work_dir)
        if event is not None:
            if progress is not None:
                progress.hdr_completed = max(
                    progress.hdr_completed,
                    event.frame_number,
                )
                progress.rounds = max(progress.rounds, event.frame_number)
            runtime.set_child_progress(
                child_role,
                completed=event.frame_number,
                stage="hdr",
                phase="HDR处理",
            )
            if on_hdr_ready is not None:
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
        video_event = parse_video_progress(line, spec.work_dir)
        if video_event is not None:
            runtime.set_main_stage("video_processing")
            runtime.set_child_progress(
                child_role,
                completed=video_event.completed,
                total=video_event.total,
                stage="video",
                phase="视频处理",
            )
            if not video_started:
                video_started = True
                runtime.set_phase("视频导出", str(spec.work_dir))
        elif "Creating video from " in line:
            video_started = True
            runtime.set_main_stage("video_processing")
            runtime.set_child_progress(
                child_role,
                completed=0,
                total=0,
                stage="video",
                phase="视频处理",
            )
            runtime.set_phase("视频导出", str(spec.work_dir))

    return handle
