"""Best-effort handoff from one finite task to its successor."""

from __future__ import annotations

from timelapse_manager.runtime import TaskRuntime
from timelapse_manager.service import ManagerService


def prepare_handoff(runtime: TaskRuntime, *, succeeded: bool) -> bool:
    runtime.poll_controls()
    continuation = runtime.task.get("continuation")
    if not isinstance(continuation, dict) or not continuation.get("enabled"):
        return False
    if runtime.hard_stop.is_set() or runtime.finish_after_current.is_set():
        return False
    if succeeded:
        return True
    if not runtime.task["retry"].get("enabled"):
        return False
    delay = float(runtime.task["retry"].get("delay_seconds", 0))
    runtime.set_phase("等待后继重试", f"{delay:g} 秒后创建新的 Manual 任务")
    if not runtime.sleep(delay, stop_on_finish=True):
        return False
    return not (
        runtime.hard_stop.is_set() or runtime.finish_after_current.is_set()
    )


def launch_successor(runtime: TaskRuntime) -> str:
    service = ManagerService(runtime.paths.root)
    predecessor = service.store.load(runtime.task_id)
    successor = service.chains.create_successor(predecessor)
    service.start_task(successor["id"])
    chain_id = str(predecessor["continuation"]["chain_id"])
    removed = service.chains.prune_completed(chain_id)
    runtime.log(f"已创建并启动后继任务: {successor['id']}")
    if removed:
        runtime.log("已清理过期成功任务: " + ", ".join(removed))
    return successor["id"]
