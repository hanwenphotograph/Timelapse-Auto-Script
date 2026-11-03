"""Detached daily dispatcher for durable processing-only tasks."""

from __future__ import annotations

import os
import subprocess
import threading
import time

from timelapse_manager.io_utils import load_json, save_json
from timelapse_manager.process_utils import (
    detached_creation_flags,
    process_identity,
    process_matches,
)
from timelapse_manager.processing.schedule import processing_ready
from timelapse_manager.task_store import ACTIVE_STATUSES


def processing_tasks(service):
    return [
        task
        for task in service.store.list_definitions()
        if task.get("preset") == "processing"
    ]


def ensure_scheduler(service) -> None:
    tasks = processing_tasks(service)
    if not any(
        service.store.read_state(t["id"])["status"] in ACTIVE_STATUSES | {"idle"}
        or service.store.read_state(t["id"])["phase"] == "工作进程异常退出"
        for t in tasks
    ):
        return
    with service.chains.lock("processing-scheduler-start"):
        owner_path = service.store.runtime_dir / "processing-scheduler.json"
        owner = load_json(owner_path, {})
        if process_matches(owner.get("pid"), owner.get("created_at")):
            return
        command = service._worker_command("unused")
        command = command[: command.index("_worker")] + ["_processing_scheduler"]
        environment = os.environ.copy()
        environment["TIMELAPSE_MANAGER_ROOT"] = str(service.paths.root)
        log_path = service.store.runtime_dir / "processing-scheduler.log"
        with log_path.open("a", encoding="utf-8") as output:
            child = subprocess.Popen(
                command,
                cwd=str(service.paths.root),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=detached_creation_flags(),
                start_new_session=os.name != "nt",
            )
        save_json(
            owner_path, {"pid": child.pid, "created_at": process_identity(child.pid)}
        )
        threading.Thread(
            target=child.wait, daemon=True, name="reap-processing-scheduler"
        ).start()


def dispatch_once(service) -> bool:
    """Start at most one job; report whether unfinished work still exists."""
    tasks = processing_tasks(service)
    pending = []
    for task in tasks:
        state = service.store.read_state(task["id"], reconcile=True)
        if state["status"] in ACTIVE_STATUSES:
            return True
        if state["status"] == "failed" and state["phase"] == "工作进程异常退出":
            # Children may outlive a killed worker; start_task checks them before retrying.
            state.update(status="idle", phase="等待恢复集中处理")
            service.store.write_state(task["id"], state)
        if state["status"] == "idle":
            pending.append(task)
    pending.sort(key=lambda task: task["deferred_processing"]["ready_at"])
    for task in pending:
        data = task["deferred_processing"]
        if not processing_ready(service.config.project, data["ready_at"]):
            continue
        source = service.store.read_state(data["source_task_id"], reconcile=True)
        if source["status"] in ACTIVE_STATUSES:
            continue
        try:
            service.start_task(task["id"])
        except Exception as exc:
            # Missing dependencies retain a failed, manually restartable job.
            state = service.store.read_state(task["id"])
            state.update(status="failed", phase="集中处理启动失败", message=str(exc))
            service.store.write_state(task["id"], state)
        break
    return bool(pending)


def run_scheduler(root=None) -> int:
    from timelapse_manager.service import ManagerService

    service = ManagerService(root, start_scheduler=False)
    while True:
        service.reload()
        # Also protects against two manually invoked dispatcher processes.
        with service.chains.lock("processing-dispatch"):
            unfinished = dispatch_once(service)
        if not unfinished:
            # Serialize shutdown with enqueue/start to avoid losing a wakeup.
            with service.chains.lock("processing-scheduler-start"):
                if not dispatch_once(service):
                    owner_path = service.store.runtime_dir / "processing-scheduler.json"
                    owner = load_json(owner_path, {})
                    if owner.get("pid") == os.getpid():
                        owner_path.unlink(missing_ok=True)
                    return 0
        time.sleep(1)
