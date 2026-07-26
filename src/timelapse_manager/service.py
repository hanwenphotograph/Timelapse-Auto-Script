"""Shared management service used by both CLI and GUI."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from timelapse_manager.config import ConfigManager, LoadedConfig
from timelapse_manager.errors import TaskError
from timelapse_manager.io_utils import now_iso
from timelapse_manager.paths import AppPaths
from timelapse_manager.presets import validate_task
from timelapse_manager.process_utils import (
    detached_creation_flags,
    process_identity,
    process_matches,
    resolve_command,
    terminate_tree,
)
from timelapse_manager.task_chain import TaskChainManager
from timelapse_manager.task_store import ACTIVE_STATUSES, TaskStore


class ManagerService:
    def __init__(self, root: Path | None = None):
        self.paths = AppPaths.discover(root)
        self.config_manager = ConfigManager(self.paths)
        self.config: LoadedConfig
        self.store: TaskStore
        self.chains: TaskChainManager
        self.reload()

    def reload(self) -> None:
        self.config = self.config_manager.load(create=True)
        self.store = TaskStore(self.config)
        self.store.ensure()
        self.chains = TaskChainManager(self.store)

    def initialize(self) -> dict[str, str]:
        self.config_manager.ensure()
        self.reload()
        self.config.auto_root.mkdir(parents=True, exist_ok=True)
        return {
            "project_config": str(self.paths.config_file),
            "webhook_config": str(self.paths.webhook_file),
            "tasks_dir": str(self.store.tasks_dir),
            "runtime_dir": str(self.store.runtime_dir),
        }

    def create_task(
        self, name: str, preset: str, task_id: str | None = None
    ) -> dict[str, Any]:
        return self.store.create(name, preset, task_id)

    def list_tasks(self) -> list[dict[str, Any]]:
        return self.store.list_with_state()

    def task_details(self, task_id: str) -> dict[str, Any]:
        return {
            "task": self.store.load(task_id),
            "state": self.store.read_state(task_id, reconcile=True),
            "definition_path": str(self.store.definition_path(task_id)),
            "log_path": str(self.store.log_path(task_id)),
        }

    def validate_task_start(
        self, task_id: str
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        self.reload()
        task = self.store.load(task_id, for_start=True)
        validate_task(task, for_start=True)
        commands = self.config.project["commands"]
        camera = resolve_command(commands["camera"])
        bracket: list[str] = []
        if task["processing"].get("enabled", True):
            bracket = resolve_command(
                commands["bracketlapse"], commands.get("bracketlapse_fallback")
            )
        return task, camera, bracket

    def start_task(self, task_id: str) -> dict[str, Any]:
        task, _, _ = self.validate_task_start(task_id)
        state = self._claim_start(task)
        with self.store.start_lock(task_id):
            command = self._worker_command(task_id)
            env = os.environ.copy()
            env["TIMELAPSE_MANAGER_ROOT"] = str(self.paths.root)
            log_path = self.store.log_path(task_id)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as output:
                try:
                    process = subprocess.Popen(
                        command,
                        cwd=str(self.paths.root),
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        creationflags=detached_creation_flags(),
                        start_new_session=os.name != "nt",
                        close_fds=True,
                    )
                except OSError as exc:
                    state.update(
                        {
                            "status": "failed",
                            "phase": "启动失败",
                            "message": str(exc),
                            "ended_at": now_iso(),
                        }
                    )
                    self.store.write_state(task_id, state)
                    raise TaskError(f"无法启动任务工作进程: {exc}") from exc
            state = self.store.read_state(task_id)
            if state["status"] in ACTIVE_STATUSES:
                state.update(
                    {
                        "runner_pid": process.pid,
                        "runner_created_at": process_identity(process.pid),
                        "message": state.get("message") or "工作进程已创建",
                    }
                )
                self.store.write_state(task_id, state)
            threading.Thread(
                target=process.wait,
                name=f"reap-worker-{task_id}-{process.pid}",
                daemon=True,
            ).start()
        return self.store.read_state(task_id, reconcile=True)

    def prepare_foreground_task(self, task_id: str) -> None:
        task, _, _ = self.validate_task_start(task_id)
        self._claim_start(task)

    def _claim_start(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = task["id"]
        metadata = self.chains.metadata(task) or {}
        with self.chains.lock(metadata.get("chain_id")):
            self.chains.validate_start(task)
            with self.store.start_lock(task_id):
                state = self.store.read_state(task_id, reconcile=True)
                if state["status"] in ACTIVE_STATUSES:
                    raise TaskError(
                        f"任务已经在运行，PID={state.get('runner_pid')}"
                    )
                self.store.clear_controls(task_id)
                state = self.store.default_state(task_id)
                state.update(
                    {
                        "status": "starting",
                        "phase": "正在启动工作进程",
                        "started_at": now_iso(),
                        "ended_at": None,
                    }
                )
                self.store.write_state(task_id, state)
                return state

    def _worker_command(self, task_id: str) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "_worker", "--task", task_id]
        source_launcher = Path(__file__).resolve().parents[2] / "timelapse.py"
        launcher = self.paths.root / "timelapse.py"
        if not launcher.is_file() and source_launcher.is_file():
            launcher = source_launcher
        return [sys.executable, str(launcher), "_worker", "--task", task_id]

    def request(self, task_id: str, action: str) -> dict[str, Any]:
        allowed = {"stop", "finish_now", "finish_after_current"}
        if action not in allowed:
            raise TaskError(f"未知控制动作: {action}")
        state = self.store.read_state(task_id, reconcile=True)
        if state["status"] not in ACTIVE_STATUSES:
            raise TaskError("任务当前没有运行")
        self.store.enqueue_control(task_id, action)
        state["status"] = "stopping" if action == "stop" else "finishing"
        labels = {
            "stop": "等待强制停止",
            "finish_now": "等待提前结束拍摄并完成处理",
            "finish_after_current": "等待当前任务或批次完成",
        }
        state["message"] = labels[action]
        self.store.write_state(task_id, state)
        return state

    def restart_task(
        self, task_id: str, timeout: float | None = None
    ) -> dict[str, Any]:
        state = self.store.read_state(task_id, reconcile=True)
        if state["status"] in ACTIVE_STATUSES:
            self.store.enqueue_control(task_id, "stop")
            limit = (
                timeout
                or float(self.config.project["runtime"]["stop_timeout_seconds"]) + 5
            )
            deadline = time.monotonic() + limit
            while time.monotonic() < deadline:
                state = self.store.read_state(task_id, reconcile=True)
                if state["status"] not in ACTIVE_STATUSES:
                    break
                time.sleep(0.2)
            else:
                pid = state.get("runner_pid")
                if process_matches(pid, state.get("runner_created_at")):
                    terminate_tree(int(pid), 2)
                state = self.store.read_state(task_id, reconcile=True)
        return self.start_task(task_id)

    def delete_task(self, task_id: str, *, purge_runtime: bool = False) -> None:
        self.store.delete(task_id, purge_runtime=purge_runtime)

    def list_processes(self) -> list[dict[str, Any]]:
        processes: list[dict[str, Any]] = []
        for item in self.store.list_with_state():
            task = item["task"]
            state = item["state"]
            runner_pid = state.get("runner_pid")
            if process_matches(runner_pid, state.get("runner_created_at")):
                processes.append(
                    {
                        "task_id": task["id"],
                        "task_name": task["name"],
                        "role": "runner",
                        "pid": runner_pid,
                        "status": state["status"],
                        "started_at": state.get("started_at"),
                        "command": "Timelapse Manager worker",
                    }
                )
            for child in state.get("children", []):
                alive = process_matches(child.get("pid"), child.get("created_at"))
                if alive or child.get("status") == "running":
                    row = dict(child)
                    row.update({"task_id": task["id"], "task_name": task["name"]})
                    row["status"] = "running" if alive else "exited"
                    processes.append(row)
        return processes

    def stop_process(self, pid: int) -> None:
        for process in self.list_processes():
            if int(process["pid"]) != int(pid):
                continue
            if process["role"] == "runner":
                self.request(process["task_id"], "stop")
            else:
                if not process_matches(pid, process.get("created_at")):
                    raise TaskError(f"PID {pid} 已退出或已被系统复用")
                terminate_tree(
                    int(pid),
                    float(self.config.project["runtime"]["stop_timeout_seconds"]),
                )
            return
        raise TaskError(f"PID {pid} 不属于当前任务列表中的活动进程")
