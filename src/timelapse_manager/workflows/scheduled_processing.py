"""Bracketlapse lifecycle and recovery for finite capture workflows."""

from __future__ import annotations

import time
from collections.abc import Callable

from timelapse_manager.child_process import ManagedChild
from timelapse_manager.runtime import HardStopRequested, TaskRuntime
from timelapse_manager.workflows.scheduled_support import (
    CaptureProgress,
    WorkSpec,
    bracket_output_handler,
)


class ScheduledProcessing:
    standby_role = "bracketlapse-standby"

    def __init__(
        self,
        runtime: TaskRuntime,
        spec: WorkSpec,
        progress: CaptureProgress,
        on_hdr_ready: Callable[[], None] | None,
        environment: dict[str, str],
    ) -> None:
        self.runtime = runtime
        self.spec = spec
        self.progress = progress
        self.on_hdr_ready = on_hdr_ready
        self.environment = environment
        configured = runtime.task["processing"].get("group_size")
        self.group_size = int(
            configured or runtime.project["eternal"]["images_per_group"]
        )
        self.standby: ManagedChild | None = None
        self.standby_code: int | None = None
        self.exited_during_capture = False

    def start(self) -> bool:
        argv = self.runtime.bracket_command + [
            "--standby",
            str(self.spec.work_dir),
            str(self.spec.work_dir),
            str(self.runtime.project["watch_quiet_seconds"]),
            "--group-size",
            str(self.group_size),
        ]
        self.standby = self._spawn(self.standby_role, argv)
        probe_seconds = float(
            self.runtime.project["runtime"]["startup_probe_seconds"]
        )
        deadline = time.monotonic() + probe_seconds
        while time.monotonic() < deadline:
            self.runtime.poll_controls()
            if self.runtime.hard_stop.is_set():
                raise HardStopRequested
            code = self.standby.poll()
            if code is not None:
                self.standby_code = code
                self.runtime.log(f"Bracketlapse standby 启动失败，退出码={code}")
                return False
            time.sleep(self.runtime.poll_interval)
        return True

    def poll_during_capture(self) -> None:
        if self.standby is None or self.standby_code is not None:
            return
        code = self.standby.poll()
        if code is None:
            return
        self.standby_code = code
        self.exited_during_capture = True
        self.runtime.set_progress(processing_recovery_required=True)
        self.runtime.log(
            "Bracketlapse standby 在拍摄期间提前退出，"
            f"退出码={code}；拍摄结束后将执行恢复处理"
        )

    def terminate(self) -> None:
        if self.standby is not None:
            self.standby.terminate()

    def finish(self, *, early: bool) -> bool:
        self.runtime.set_main_stage("waiting_processing")
        self.runtime.set_phase("等待 HDR 处理", str(self.spec.work_dir))
        if early:
            self.terminate()
            return self._run_batch("bracketlapse-process", overwrite=False)

        assert self.standby is not None
        code = self.standby_code
        if code is None:
            code = self.runtime.wait_child(self.standby)
            self.standby_code = code
        if code == 0 and not self.exited_during_capture:
            return True

        self.runtime.log(
            "Bracketlapse standby 未完成全部处理，开始从稳定的最终照片恢复"
        )
        return self._run_batch("bracketlapse-recovery", overwrite=True)

    def _run_batch(self, role: str, *, overwrite: bool) -> bool:
        argv = self.runtime.bracket_command + [
            str(self.spec.work_dir),
            "--merge-subdirs",
            "--group-size",
            str(self.group_size),
        ]
        if overwrite:
            argv.append("--overwrite")
        child = self._spawn(role, argv)
        self.runtime.set_child_progress(
            role,
            completed=self.progress.hdr_completed,
            total=self.progress.rounds,
            stage="hdr",
            phase="HDR处理",
        )
        return self.runtime.wait_child(child) == 0

    def _spawn(self, role: str, argv: list[str]) -> ManagedChild:
        return self.runtime.spawn(
            role,
            argv,
            cwd=self.spec.work_dir,
            extra_env=self.environment,
            on_line=bracket_output_handler(
                self.runtime,
                self.spec,
                self.on_hdr_ready,
                progress=self.progress,
                child_role=role,
            ),
        )
