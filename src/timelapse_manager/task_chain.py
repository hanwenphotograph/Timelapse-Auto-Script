"""Continuation-chain coordination and retention."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from timelapse_manager.errors import TaskError
from timelapse_manager.process_utils import process_matches
from timelapse_manager.task_factory import create_successor_definition
from timelapse_manager.task_store import ACTIVE_STATUSES, TaskStore


class TaskChainManager:
    def __init__(self, store: TaskStore):
        self.store = store
        self.lock_dir = store.runtime_dir / "chains"

    @staticmethod
    def metadata(task: dict[str, Any]) -> dict[str, Any] | None:
        value = task.get("continuation")
        return value if isinstance(value, dict) else None

    def validate_start(self, task: dict[str, Any]) -> None:
        metadata = self.metadata(task)
        if not metadata:
            return
        chain_id = str(metadata["chain_id"])
        for other in self._chain_tasks(chain_id):
            if other["id"] == task["id"]:
                continue
            other_meta = self.metadata(other) or {}
            if other_meta.get("previous_task_id") == task["id"]:
                raise TaskError("历史任务已有后继，不能再次启动或形成任务链分叉")
            state = self.store.read_state(other["id"], reconcile=True)
            if state["status"] in ACTIVE_STATUSES:
                raise TaskError(
                    f"同一永久任务链已有活动任务: {other['id']}"
                )

    def create_successor(self, predecessor: dict[str, Any]) -> dict[str, Any]:
        metadata = self.metadata(predecessor)
        if not metadata or not metadata.get("enabled"):
            raise TaskError("当前任务未启用永久接力")
        with self.lock(str(metadata["chain_id"])):
            for task in self._chain_tasks(str(metadata["chain_id"])):
                task_meta = self.metadata(task) or {}
                if task_meta.get("previous_task_id") == predecessor["id"]:
                    return task
            task_id = self._new_task_id()
            successor = create_successor_definition(
                self.store.config, task_id, predecessor
            )
            self.store.add_definition(successor)
            return successor

    def prune_completed(
        self, chain_id: str, *, now: datetime | None = None
    ) -> list[str]:
        retention = int(
            self.store.config.project["runtime"]["task_history_retention_days"]
        )
        cutoff = (now or datetime.now().astimezone()) - timedelta(days=retention)
        removed: list[str] = []
        for task in self._chain_tasks(chain_id):
            state = self.store.read_state(task["id"], reconcile=True)
            if state["status"] != "completed" or not state.get("ended_at"):
                continue
            try:
                ended_at = datetime.fromisoformat(str(state["ended_at"]))
            except ValueError:
                continue
            if ended_at.tzinfo is None:
                ended_at = ended_at.astimezone()
            if ended_at >= cutoff:
                continue
            self.store.delete(task["id"], purge_runtime=True)
            removed.append(task["id"])
        return removed

    def _chain_tasks(self, chain_id: str) -> list[dict[str, Any]]:
        return [
            task
            for task in self.store.list_definitions()
            if (self.metadata(task) or {}).get("chain_id") == chain_id
        ]

    def _new_task_id(self) -> str:
        while True:
            task_id = self.store.generate_id("scheduled-loop")
            if not self.store.definition_path(task_id).exists():
                return task_id

    @contextmanager
    def lock(self, chain_id: str | None) -> Iterator[None]:
        if not chain_id:
            yield
            return
        self.store.validate_id(chain_id)
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        path = self.lock_dir / f"{chain_id}.lock"
        descriptor = self._acquire(path)
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            descriptor = -1
            yield
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _acquire(path: Path) -> int:
        deadline = time.monotonic() + 10
        while True:
            try:
                return os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                try:
                    owner = int(path.read_text(encoding="ascii").strip())
                    age = time.time() - path.stat().st_mtime
                except (OSError, ValueError):
                    owner, age = 0, 31
                if not process_matches(owner) or age > 30:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TaskError("等待永久任务链操作锁超时") from exc
                time.sleep(0.05)
