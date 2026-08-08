"""Best-effort handoff from one finite task to its successor."""

from __future__ import annotations

from typing import Literal

from timelapse_manager.runtime import TaskRuntime
from timelapse_manager.service import ManagerService


HandoffKind = Literal["scheduled", "retry"]


def prepare_handoff(
    runtime: TaskRuntime,
    *,
    succeeded: bool,
) -> HandoffKind | None:
    runtime.poll_controls()
    continuation = runtime.task.get("continuation")
    if not isinstance(continuation, dict) or not continuation.get("enabled"):
        return None
    if runtime.hard_stop.is_set() or runtime.finish_after_current.is_set():
        return None
    if succeeded:
        return "scheduled"
    if not runtime.task["retry"].get("enabled"):
        return None
    attempt = int(continuation.get("retry_attempt", 0)) + 1
    maximum = int(runtime.project["runtime"]["max_retry_attempts"])
    if attempt > maximum:
        runtime.log(f"连续失败已达到重试上限 {maximum} 次，不再创建后继任务")
        return None
    delay = float(runtime.task["retry"].get("delay_seconds", 0))
    runtime.set_phase(
        "等待后继重试",
        f"第 {attempt}/{maximum} 次重试将在 {delay:g} 秒后创建",
    )
    if not runtime.sleep(delay, stop_on_finish=True):
        return None
    if runtime.hard_stop.is_set() or runtime.finish_after_current.is_set():
        return None
    return "retry"


def launch_successor(runtime: TaskRuntime, kind: HandoffKind) -> str:
    service = ManagerService(runtime.paths.root)
    predecessor = service.store.load(runtime.task_id)
    successor = service.chains.create_successor(
        predecessor,
        retry=kind == "retry",
    )
    service.start_task(successor["id"])
    chain_id = str(predecessor["continuation"]["chain_id"])
    removed = service.chains.prune_completed(chain_id)
    runtime.log(f"已创建并启动后继任务: {successor['id']}")
    if removed:
        runtime.log("已清理过期成功任务: " + ", ".join(removed))
    return successor["id"]
