"""Finite Manual capture workflow."""

from __future__ import annotations

import time
from datetime import datetime

from timelapse_manager.errors import ConfigError, TaskError
from timelapse_manager.runtime import HardStopRequested, TaskRuntime
from timelapse_manager.workflows.scheduled_finish import ScheduledFinisher
from timelapse_manager.workflows.scheduled_support import (
    CaptureProgress,
    WorkSpec,
    bracket_output_handler,
    camera_output_handler,
)


class ScheduledWorkflow:
    def __init__(self, runtime: TaskRuntime):
        self.runtime = runtime
        self.task = runtime.task
        self.project = runtime.project
        self.finisher = ScheduledFinisher(runtime)

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
            end = datetime.fromisoformat(f"{capture['end_date']}T{capture['end_at']}")
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

    def _run_once(self, spec: WorkSpec) -> bool:
        spec.work_dir.mkdir(parents=True, exist_ok=True)
        preserve_names = frozenset(entry.name for entry in spec.work_dir.iterdir())
        capture_progress = CaptureProgress()
        interval = self.task["capture"].get("interval_seconds")
        if interval is None:
            interval = self.project["capture_interval_seconds"]
        processing_enabled = bool(self.task["processing"].get("enabled", True))
        self.runtime.set_main_stage("waiting_capture")
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
        score_session = (
            self.runtime.sunset_score.start_stream(spec.work_dir, spec.score_label)
            if processing_enabled
            else None
        )
        standby = None
        standby_role = "bracketlapse-standby"
        if processing_enabled:
            standby_argv = self.runtime.bracket_command + [
                "--standby",
                str(spec.work_dir),
                str(spec.work_dir),
                str(self.project["watch_quiet_seconds"]),
            ]
            standby = self.runtime.spawn(
                standby_role,
                standby_argv,
                cwd=spec.work_dir,
                extra_env=env,
                on_line=bracket_output_handler(
                    self.runtime,
                    spec,
                    score_session.scan if score_session else None,
                    progress=capture_progress,
                    child_role=standby_role,
                ),
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
                    return self.finisher.finish(
                        spec,
                        False,
                        score_session,
                        capture_started=False,
                        preserve_names=preserve_names,
                    )
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
            on_line=camera_output_handler(
                self.runtime,
                spec,
                capture_progress,
                hdr_role=standby_role if processing_enabled else None,
            ),
        )
        self.runtime.notify_async(
            "camera_process_started", f"camera-timelapse 已启动，目录 {spec.work_dir}"
        )
        early = False
        while True:
            self.runtime.poll_controls()
            if self.runtime.hard_stop.is_set():
                camera.terminate()
                if standby is not None:
                    standby.terminate()
                raise HardStopRequested
            if self.runtime.finish_now.is_set() and camera.poll() is None:
                early = True
                self.runtime.set_phase("提前结束拍摄", "正在停止相机并转入 HDR 处理")
                camera.terminate()
            camera_code = camera.poll()
            if camera_code is not None:
                break
            time.sleep(self.runtime.poll_interval)

        success = camera_code == 0 or early
        if not success:
            self.runtime.log(f"camera-timelapse 异常退出，退出码={camera_code}")
            if standby is not None:
                standby.terminate()
        elif processing_enabled and early:
            assert standby is not None
            standby.terminate()
            merge_argv = self.runtime.bracket_command + [
                str(spec.work_dir),
                "--merge-subdirs",
            ]
            standby_role = "bracketlapse-process"
            standby = self.runtime.spawn(
                standby_role,
                merge_argv,
                cwd=spec.work_dir,
                extra_env=env,
                on_line=bracket_output_handler(
                    self.runtime,
                    spec,
                    score_session.scan if score_session else None,
                    progress=capture_progress,
                    child_role=standby_role,
                ),
            )
            self.runtime.set_child_progress(
                standby_role,
                completed=capture_progress.hdr_completed,
                total=capture_progress.rounds,
                stage="hdr",
                phase="HDR处理",
            )
        if processing_enabled and success:
            assert standby is not None
            self.runtime.set_main_stage("waiting_processing")
            self.runtime.set_phase("等待 HDR 处理", str(spec.work_dir))
            code = self.runtime.wait_child(standby)
            success = code == 0
        return self.finisher.finish(
            spec,
            success,
            score_session,
            capture_started=capture_progress.started,
            preserve_names=preserve_names,
        )
