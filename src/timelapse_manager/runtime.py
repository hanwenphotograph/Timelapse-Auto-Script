"""Runtime context shared by task workflows."""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from pathlib import Path
from typing import Callable

from timelapse_manager.child_process import ManagedChild
from timelapse_manager.config import ConfigManager
from timelapse_manager.io_utils import now_iso
from timelapse_manager.paths import AppPaths
from timelapse_manager.process_utils import process_identity, resolve_command
from timelapse_manager.task_store import TaskStore
from timelapse_manager.webhook import WebhookClient


class HardStopRequested(Exception):
    """Internal control-flow exception for a force stop."""


class TaskRuntime:
    def __init__(
        self, task_id: str, root: Path | None = None, *, console: bool = False
    ):
        self.paths = AppPaths.discover(root)
        self.loaded = ConfigManager(self.paths).load()
        self.store = TaskStore(self.loaded)
        self.task = self.store.load(task_id, for_start=True)
        self.task_id = task_id
        self.project = self.loaded.project
        self.auto_root = self.loaded.auto_root
        self.runtime_options = self.project["runtime"]
        self.poll_interval = float(self.runtime_options["poll_interval_seconds"])
        self.stop_timeout = float(self.runtime_options["stop_timeout_seconds"])
        commands = self.project["commands"]
        self.camera_command = resolve_command(commands["camera"])
        self.bracket_command: list[str] = []
        if self.task["processing"].get("enabled", True):
            self.bracket_command = resolve_command(
                commands["bracketlapse"], commands.get("bracketlapse_fallback")
            )

        self._state_lock = threading.RLock()
        self._children_lock = threading.RLock()
        self._children: dict[int, ManagedChild] = {}
        self.hard_stop = threading.Event()
        self.finish_now = threading.Event()
        self.finish_after_current = threading.Event()
        self._logger = self._create_logger(console)
        self.webhook = WebhookClient(self.loaded.webhook, self.log)
        self.state = self.store.default_state(task_id)
        self.state.update(
            {
                "status": "running",
                "phase": "工作进程已启动",
                "runner_pid": os.getpid(),
                "runner_created_at": process_identity(os.getpid()),
                "started_at": now_iso(),
                "ended_at": None,
            }
        )
        self.store.write_state(self.task_id, self.state)

    def _create_logger(self, console: bool) -> logging.Logger:
        logger = logging.getLogger(f"timelapse.task.{self.task_id}.{os.getpid()}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        formatter = logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        log_path = self.store.log_path(self.task_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        if console:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
        return logger

    def log(self, message: str) -> None:
        self._logger.info(message)

    def update_state(self, **values: object) -> None:
        with self._state_lock:
            self.state.update(values)
            self.store.write_state(self.task_id, self.state)

    def set_phase(self, phase: str, message: str | None = None) -> None:
        values: dict[str, object] = {"phase": phase}
        if message is not None:
            values["message"] = message
        self.update_state(**values)
        self.log(phase if message is None else f"{phase}: {message}")

    def set_progress(self, **values: object) -> None:
        with self._state_lock:
            progress = dict(self.state.get("progress", {}))
            progress.update(values)
            self.state["progress"] = progress
            self.store.write_state(self.task_id, self.state)

    def notify(self, event: str, content: str) -> None:
        self.webhook.notify(event, content)

    def notify_async(self, event: str, content: str) -> None:
        if not self.webhook.enabled:
            return
        threading.Thread(
            target=self.webhook.notify,
            args=(event, content),
            name=f"webhook-{event}",
            daemon=True,
        ).start()

    def child_started(self, child: ManagedChild) -> None:
        assert child.pid is not None
        with self._children_lock:
            self._children[child.pid] = child
        with self._state_lock:
            children = list(self.state.get("children", []))
            children.append(
                {
                    "role": child.role,
                    "pid": child.pid,
                    "created_at": child.created_at,
                    "status": "running",
                    "started_at": now_iso(),
                    "ended_at": None,
                    "exit_code": None,
                    "command": child.command_text,
                }
            )
            self.state["children"] = children[-30:]
            self.store.write_state(self.task_id, self.state)

    def child_exited(self, child: ManagedChild, code: int) -> None:
        if child.pid is None:
            return
        with self._children_lock:
            self._children.pop(child.pid, None)
        with self._state_lock:
            children = list(self.state.get("children", []))
            for record in reversed(children):
                if record.get("pid") == child.pid and record.get("status") == "running":
                    record.update(
                        {
                            "status": "completed" if code == 0 else "failed",
                            "ended_at": now_iso(),
                            "exit_code": code,
                        }
                    )
                    break
            self.state["children"] = children[-30:]
            self.store.write_state(self.task_id, self.state)

    def spawn(
        self,
        role: str,
        argv: list[str],
        *,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
        on_line: Callable[[str], None] | None = None,
    ) -> ManagedChild:
        environment = os.environ.copy()
        environment.update(
            {str(key): str(value) for key, value in self.task["environment"].items()}
        )
        if extra_env:
            environment.update(
                {str(key): str(value) for key, value in extra_env.items()}
            )
        return ManagedChild(
            role,
            argv,
            cwd=cwd,
            env=environment,
            log=self.log,
            on_line=on_line,
            on_started=self.child_started,
            on_exited=self.child_exited,
            stop_timeout=self.stop_timeout,
        ).start()

    def poll_controls(self) -> None:
        for control in self.store.pop_controls(self.task_id):
            action = control.get("action")
            if action == "stop":
                self.log("收到强制停止请求")
                self.hard_stop.set()
                self.update_state(status="stopping", message="正在强制停止全部子进程")
            elif action == "finish_now":
                self.log("收到立即结束拍摄并完成处理请求")
                self.finish_now.set()
                self.finish_after_current.set()
                self.update_state(
                    status="finishing", message="将立即结束拍摄并完成处理"
                )
            elif action == "finish_after_current":
                self.log("收到当前任务或批次完成后停止请求")
                self.finish_after_current.set()
                self.update_state(
                    status="finishing", message="将在当前任务或批次完成后停止"
                )
        if self.hard_stop.is_set():
            self.terminate_all()

    def install_signal_handlers(self) -> None:
        def request_stop(signum: int, _frame: object) -> None:
            self.log(f"收到系统信号 {signum}，准备停止")
            self.hard_stop.set()

        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, request_stop)

    def terminate_all(self) -> None:
        with self._children_lock:
            children = list(self._children.values())
        for child in children:
            try:
                child.terminate()
            except Exception as exc:
                self.log(f"停止 {child.role} 时出现警告: {exc}")

    def sleep(self, seconds: float, *, stop_on_finish: bool = False) -> bool:
        deadline = time.monotonic() + max(0, seconds)
        while time.monotonic() < deadline:
            self.poll_controls()
            if self.hard_stop.is_set() or (
                stop_on_finish and self.finish_after_current.is_set()
            ):
                return False
            time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))
        return True

    def wait_child(self, child: ManagedChild) -> int:
        while True:
            self.poll_controls()
            if self.hard_stop.is_set():
                child.terminate()
                raise HardStopRequested
            code = child.poll()
            if code is not None:
                return code
            time.sleep(self.poll_interval)

    def finish(
        self, status: str, phase: str, exit_code: int, message: str = ""
    ) -> None:
        self.update_state(
            status=status,
            phase=phase,
            message=message,
            exit_code=exit_code,
            ended_at=now_iso(),
            runner_pid=None,
            runner_created_at=None,
        )

    def close(self) -> None:
        self.terminate_all()
        for handler in list(self._logger.handlers):
            handler.flush()
            handler.close()
            self._logger.removeHandler(handler)
