"""Finite Manual capture workflow."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from timelapse_manager.errors import ConfigError, TaskError
from timelapse_manager.maintenance import check_disk_space, cleanup_work_directory
from timelapse_manager.runtime import HardStopRequested, TaskRuntime


@dataclass(frozen=True)
class WorkSpec:
    label: str
    work_dir: Path
    start_date: str
    start_at: str
    end_date: str
    end_at: str


class ScheduledWorkflow:
    def __init__(self, runtime: TaskRuntime):
        self.runtime = runtime
        self.task = runtime.task
        self.project = runtime.project

    def run(self) -> None:
        spec = self._work_spec()
        if not self._run_once(spec):
            raise TaskError("任务失败，请查看任务日志")

    def _work_spec(self) -> WorkSpec:
        capture = self.task["capture"]
        work_dir = self.runtime.paths.resolve_from_root(str(capture["work_dir"]))
        try:
            start = datetime.fromisoformat(
                f"{capture['start_date']}T{capture['start_at']}"
            )
            end = datetime.fromisoformat(
                f"{capture['end_date']}T{capture['end_at']}"
            )
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                "手动任务日期必须是 YYYY-MM-DD，时间必须是 HH:MM"
            ) from exc
        if start >= end:
            raise ConfigError("手动任务结束日期时间必须晚于开始日期时间")
        return WorkSpec(
            "手动",
            work_dir,
            str(capture["start_date"]),
            str(capture["start_at"]),
            str(capture["end_date"]),
            str(capture["end_at"]),
        )

    def _camera_output_handler(self, spec: WorkSpec):
        capture_started = False
        capture_ended = False

        def handle(line: str) -> None:
            nonlocal capture_started, capture_ended
            if "Starting capture round " in line and not capture_started:
                capture_started = True
                self.runtime.set_phase(
                    "正在拍摄", f"{spec.label}任务已进入实际拍摄阶段"
                )
                self.runtime.notify_async(
                    "entered_key_node",
                    f"camera-timelapse 真正开始拍摄，日期 {spec.start_date}，目录 {spec.work_dir}",
                )
            if (
                "Scheduled end time " in line
                and "reached; stopping after this round" in line
            ):
                if capture_started and not capture_ended:
                    capture_ended = True
                    self.runtime.set_phase("拍摄即将结束", "已到达计划结束时间")
                    self.runtime.notify_async(
                        "exited_key_node",
                        f"camera-timelapse 已按计划结束，目录 {spec.work_dir}",
                    )

        return handle

    def _bracket_output_handler(self, spec: WorkSpec):
        enfuse_started = False
        deflick_started = False

        def handle(line: str) -> None:
            nonlocal enfuse_started, deflick_started
            if "Fusing " in line and not enfuse_started:
                enfuse_started = True
                self.runtime.set_phase("HDR 融合", str(spec.work_dir))
                self.runtime.notify_async(
                    "entered_key_node", f"enfuse 开始融合，目录 {spec.work_dir}"
                )
            if "Deflickering fused frames." in line and not deflick_started:
                deflick_started = True
                self.runtime.set_phase("去闪处理", str(spec.work_dir))
                self.runtime.notify_async(
                    "entered_key_node",
                    f"simple-deflicker 开始去闪，目录 {spec.work_dir}",
                )
            if "Creating video from " in line or line.rstrip().endswith("Done."):
                self.runtime.set_phase("视频导出", str(spec.work_dir))

        return handle

    def _run_once(self, spec: WorkSpec) -> bool:
        spec.work_dir.mkdir(parents=True, exist_ok=True)
        interval = self.task["capture"].get("interval_seconds")
        if interval is None:
            interval = self.project["capture_interval_seconds"]
        processing_enabled = bool(self.task["processing"].get("enabled", True))
        standby = None
        self.runtime.set_phase(
            "守护拍摄计划",
            f"{spec.label} {spec.start_date} {spec.start_at}-{spec.end_date} {spec.end_at}",
        )
        self.runtime.notify(
            "runner_started",
            f"{spec.label}延时摄影进入守护状态，计划 {spec.start_date} {spec.start_at} 至 {spec.end_date} {spec.end_at}，目录 {spec.work_dir}",
        )
        env = {
            "BRACKLAPSE_RUN_DATE": spec.start_date,
            "BRACKLAPSE_RUN_START_AT": spec.start_at,
            "BRACKLAPSE_RUN_END_AT": spec.end_at,
        }
        if processing_enabled:
            standby_argv = self.runtime.bracket_command + [
                "--standby",
                str(spec.work_dir),
                str(spec.work_dir),
                str(self.project["watch_quiet_seconds"]),
            ]
            standby = self.runtime.spawn(
                "bracketlapse-standby",
                standby_argv,
                cwd=spec.work_dir,
                extra_env=env,
                on_line=self._bracket_output_handler(spec),
            )
            probe_seconds = float(self.project["runtime"]["startup_probe_seconds"])
            deadline = time.monotonic() + probe_seconds
            while time.monotonic() < deadline:
                self.runtime.poll_controls()
                if self.runtime.hard_stop.is_set():
                    raise HardStopRequested
                code = standby.poll()
                if code is not None:
                    self.runtime.log(f"Bracketlapse standby 启动失败，退出码={code}")
                    return self._finish(spec, False)
                time.sleep(self.runtime.poll_interval)

        camera_argv = self.runtime.camera_command + [
            str(spec.work_dir),
            "--start-at",
            spec.start_at,
            "--start-day",
            spec.start_date,
            "--end-at",
            spec.end_at,
            "--end-day",
            spec.end_date,
            "--interval",
            str(interval),
        ]
        camera = self.runtime.spawn(
            "camera-timelapse",
            camera_argv,
            cwd=spec.work_dir,
            extra_env={"PYTHONUNBUFFERED": "1"},
            on_line=self._camera_output_handler(spec),
        )
        self.runtime.notify_async(
            "camera_process_started", f"camera-timelapse 已启动，目录 {spec.work_dir}"
        )
        early = False
        while True:
            self.runtime.poll_controls()
            if self.runtime.hard_stop.is_set():
                camera.terminate()
                if standby:
                    standby.terminate()
                raise HardStopRequested
            if self.runtime.finish_now.is_set() and camera.poll() is None:
                early = True
                self.runtime.set_phase("提前结束拍摄", "正在停止相机并转入后期处理")
                camera.terminate()
            camera_code = camera.poll()
            if camera_code is not None:
                break
            time.sleep(self.runtime.poll_interval)

        success = camera_code == 0 or early
        if not success:
            self.runtime.log(f"camera-timelapse 异常退出，退出码={camera_code}")
            if standby:
                standby.terminate()
        elif processing_enabled and early:
            assert standby is not None
            standby.terminate()
            merge_argv = self.runtime.bracket_command + [
                str(spec.work_dir),
                "--merge-subdirs",
            ]
            standby = self.runtime.spawn(
                "bracketlapse-process",
                merge_argv,
                cwd=spec.work_dir,
                extra_env=env,
                on_line=self._bracket_output_handler(spec),
            )

        if processing_enabled and success:
            assert standby is not None
            self.runtime.set_phase("等待后期处理", str(spec.work_dir))
            code = self.runtime.wait_child(standby)
            success = code == 0
        return self._finish(spec, success)

    def _finish(self, spec: WorkSpec, success: bool) -> bool:
        cleanup = self.task["cleanup"]
        if cleanup.get("enabled") and (success or cleanup.get("on_failure")):
            try:
                cleanup_work_directory(
                    spec.work_dir,
                    list(cleanup["keep_directories"]),
                    self.runtime.log,
                    protected_paths=[self.runtime.paths.root, self.runtime.auto_root],
                )
            except (OSError, TaskError) as exc:
                self.runtime.log(f"清理工作目录失败: {exc}")
                success = False
        threshold = float(self.project["disk_space_warning_threshold_gb"])
        remaining = check_disk_space(spec.work_dir, threshold, self.runtime.log)
        if threshold > 0 and remaining < threshold:
            self.runtime.notify_async(
                "disk_space_warning",
                f"磁盘剩余 {remaining:.2f}GB，低于阈值 {threshold:g}GB",
            )
        if success:
            self.runtime.webhook.notify_image(
                "webhook-image",
                f"图片推送：{spec.label}延时摄影，日期 {spec.start_date}，时间 {spec.start_at}-{spec.end_at}",
                spec.work_dir,
            )
        self.runtime.notify_async(
            "ended",
            f"任务{'完成' if success else '失败'}：{spec.label}，目录 {spec.work_dir}",
        )
        return success
