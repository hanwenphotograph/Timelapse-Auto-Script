"""Detached task worker entry point."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from timelapse_manager.errors import TimelapseError
from timelapse_manager.runtime import HardStopRequested, TaskRuntime


def _execute(runtime: TaskRuntime) -> None:
    runtime.install_signal_handlers()
    runtime.log(
        f"任务工作进程启动，模式={runtime.task['preset']}，PID={runtime.state['runner_pid']}"
    )
    if runtime.task["preset"] == "eternal":
        from timelapse_manager.workflows.eternal import EternalWorkflow

        EternalWorkflow(runtime).run()
    else:
        from timelapse_manager.workflows.scheduled import ScheduledWorkflow

        ScheduledWorkflow(runtime).run()
    if runtime.hard_stop.is_set():
        raise HardStopRequested


def run_worker(task_id: str, root: Path | None = None, *, console: bool = False) -> int:
    try:
        runtime = TaskRuntime(task_id, root, console=console)
    except (TimelapseError, OSError, ValueError) as exc:
        print(f"任务工作进程初始化失败: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "任务工作进程初始化发生未处理异常:\n" + traceback.format_exc(),
            file=sys.stderr,
        )
        return 1

    status, phase, code, message = "completed", "任务已完成", 0, ""
    try:
        _execute(runtime)
        runtime.log("任务已正常完成")
    except HardStopRequested:
        status, phase, code = "stopped", "任务已强制停止", 130
        runtime.log("任务已强制停止")
    except (TimelapseError, OSError, ValueError) as exc:
        status, phase, code, message = "failed", "任务失败", 1, str(exc)
        runtime.log(f"任务失败: {exc}")
    except Exception as exc:
        status, phase, code, message = (
            "failed",
            "任务发生未处理异常",
            1,
            str(exc),
        )
        runtime.log("任务发生未处理异常:\n" + traceback.format_exc())

    try:
        from timelapse_manager.task_handoff import launch_successor, prepare_handoff

        try:
            handoff = prepare_handoff(runtime, succeeded=status == "completed")
        except Exception as exc:
            handoff = False
            runtime.log(f"准备后继任务失败: {exc}")
        if runtime.hard_stop.is_set():
            status, phase, code, message = "stopped", "任务已强制停止", 130, ""
        runtime.finish(status, phase, code, message)
        if handoff:
            try:
                launch_successor(runtime)
            except Exception as exc:
                runtime.log(f"创建或启动后继任务失败: {exc}")
    finally:
        runtime.close()
    return code
