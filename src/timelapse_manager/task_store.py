"""Persistent task definitions, states, controls, and logs."""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from timelapse_manager.config import LoadedConfig
from timelapse_manager.errors import ConfigError, TaskError
from timelapse_manager.io_utils import (
    deep_merge,
    load_json,
    load_yaml,
    now_iso,
    parse_yaml,
    save_json,
    save_yaml,
    yaml_text,
)
from timelapse_manager.presets import (
    LEGACY_SCHEDULED_PRESETS,
    normalize_task,
    validate_task,
)
from timelapse_manager.process_utils import process_matches
from timelapse_manager.task_factory import (
    create_task_definition,
    migrate_legacy_scheduled,
)


TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$")
ACTIVE_STATUSES = {"starting", "running", "stopping", "finishing"}


def _slug(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-_").lower()
    return result[:24] or "task"


class TaskStore:
    def __init__(self, config: LoadedConfig):
        self.config = config
        self.tasks_dir = config.tasks_dir
        self.runtime_dir = config.runtime_dir
        self.task_runtime_dir = self.runtime_dir / "tasks"
        self._write_lock = threading.RLock()

    def ensure(self) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.task_runtime_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate_id(task_id: str) -> None:
        if not TASK_ID_PATTERN.fullmatch(task_id):
            raise TaskError("任务 ID 只能包含 3-64 位字母、数字、下划线和连字符")

    def definition_path(self, task_id: str) -> Path:
        self.validate_id(task_id)
        return self.tasks_dir / f"{task_id}.yaml"

    def runtime_path(self, task_id: str) -> Path:
        self.validate_id(task_id)
        return self.task_runtime_dir / task_id

    def state_path(self, task_id: str) -> Path:
        return self.runtime_path(task_id) / "state.json"

    def log_path(self, task_id: str) -> Path:
        return self.runtime_path(task_id) / "task.log"

    def create(
        self, name: str, preset: str, task_id: str | None = None
    ) -> dict[str, Any]:
        self.ensure()
        generated = task_id or self.generate_id(preset)
        task = create_task_definition(self.config, generated, name, preset)
        self.add_definition(task)
        return task

    @staticmethod
    def generate_id(prefix: str) -> str:
        return f"{_slug(prefix)}-{int(time.time())}-{uuid.uuid4().hex[:4]}"

    def add_definition(self, task: dict[str, Any]) -> None:
        generated = str(task.get("id", ""))
        self.validate_id(generated)
        path = self.definition_path(generated)
        if path.exists():
            raise TaskError(f"任务已存在: {generated}")
        validate_task(normalize_task(task))
        save_yaml(path, task)
        self.write_state(generated, self.default_state(generated))

    def list_definitions(self) -> list[dict[str, Any]]:
        self.ensure()
        tasks: list[dict[str, Any]] = []
        for path in sorted(self.tasks_dir.glob("*.yaml")):
            try:
                task = self._load_path(path)
                tasks.append(task)
            except (ConfigError, TaskError) as exc:
                tasks.append(
                    {
                        "id": path.stem,
                        "name": path.stem,
                        "preset": "invalid",
                        "_error": str(exc),
                    }
                )
        return tasks

    def _load_path(self, path: Path) -> dict[str, Any]:
        raw = load_yaml(path)
        if raw.get("id") != path.stem:
            raise TaskError(f"任务文件名与 id 不一致: {path.name}")
        if raw.get("preset") in LEGACY_SCHEDULED_PRESETS:
            state = self.read_state(path.stem, reconcile=True)
            if state["status"] not in ACTIVE_STATUSES:
                raw = migrate_legacy_scheduled(self.config, raw)
                save_yaml(path, raw)
        task = normalize_task(raw)
        validate_task(task)
        return task

    def load(self, task_id: str, *, for_start: bool = False) -> dict[str, Any]:
        path = self.definition_path(task_id)
        if not path.exists():
            raise TaskError(f"任务不存在: {task_id}")
        task = self._load_path(path)
        validate_task(task, for_start=for_start)
        return task

    def read_text(self, task_id: str) -> str:
        path = self.definition_path(task_id)
        if not path.exists():
            raise TaskError(f"任务不存在: {task_id}")
        self.load(task_id)
        return path.read_text(encoding="utf-8")

    def save_text(self, task_id: str, text: str) -> dict[str, Any]:
        current_state = self.read_state(task_id, reconcile=True)
        if current_state["status"] in ACTIVE_STATUSES:
            raise TaskError("运行中的任务不能修改配置")
        parsed = parse_yaml(text, "任务 YAML")
        if parsed.get("id") != task_id:
            raise TaskError("任务 YAML 中的 id 不能修改")
        current = self.load(task_id)
        merged = normalize_task(parsed)
        validate_task(merged)
        self._validate_chain_identity(current, merged)
        save_yaml(self.definition_path(task_id), parsed)
        return merged

    @staticmethod
    def _validate_chain_identity(
        current: dict[str, Any], replacement: dict[str, Any]
    ) -> None:
        current_meta = current.get("continuation")
        replacement_meta = replacement.get("continuation")
        if bool(current_meta) != bool(replacement_meta):
            raise TaskError("任务 continuation 链身份不能添加或删除")
        if not current_meta:
            return
        immutable = {
            "chain_id",
            "chain_name",
            "sequence",
            "source_preset",
            "previous_task_id",
        }
        changed = [
            key
            for key in immutable
            if current_meta.get(key) != replacement_meta.get(key)
        ]
        if changed:
            raise TaskError("任务链身份字段不能修改: " + ", ".join(sorted(changed)))

    def normalized_text(self, task_id: str) -> str:
        return yaml_text(self.load(task_id))

    @staticmethod
    def default_state(task_id: str) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "status": "idle",
            "phase": "未启动",
            "message": "",
            "runner_pid": None,
            "runner_created_at": None,
            "started_at": None,
            "updated_at": now_iso(),
            "ended_at": None,
            "exit_code": None,
            "children": [],
            "progress": {},
        }

    def read_state(self, task_id: str, *, reconcile: bool = False) -> dict[str, Any]:
        default = self.default_state(task_id)
        missing = object()
        state: Any = missing
        for attempt in range(20):
            state = load_json(self.state_path(task_id), missing)
            if state is not missing:
                break
            if attempt < 19:
                time.sleep(0.005 * (attempt + 1))
        if state is missing:
            state = default
        if not isinstance(state, dict):
            state = default
        state = deep_merge(default, state)
        if reconcile and state["status"] in ACTIVE_STATUSES:
            if state["status"] == "starting" and state.get("runner_pid") is None:
                return state
            if not process_matches(
                state.get("runner_pid"), state.get("runner_created_at")
            ):
                state = self._reconcile_missing_runner(task_id)
        return state

    def _reconcile_missing_runner(self, task_id: str) -> dict[str, Any]:
        """Confirm a dead runner without overwriting a newer terminal state."""
        default = self.default_state(task_id)
        with self._write_lock:
            with self._state_file_lock(task_id):
                latest = load_json(self.state_path(task_id), default)
                if not isinstance(latest, dict):
                    latest = default
                latest = deep_merge(default, latest)
                if latest["status"] not in ACTIVE_STATUSES:
                    return latest
                if latest["status"] == "starting" and latest.get("runner_pid") is None:
                    return latest
                if process_matches(
                    latest.get("runner_pid"), latest.get("runner_created_at")
                ):
                    return latest
                latest.update(
                    {
                        "status": "failed",
                        "phase": "工作进程异常退出",
                        "message": "记录的任务工作进程已不存在",
                        "runner_pid": None,
                        "runner_created_at": None,
                        "ended_at": now_iso(),
                        "updated_at": now_iso(),
                    }
                )
                save_json(self.state_path(task_id), latest)
                return latest

    def write_state(self, task_id: str, state: dict[str, Any]) -> None:
        self.ensure()
        state["task_id"] = task_id
        state["updated_at"] = now_iso()
        with self._write_lock:
            with self._state_file_lock(task_id):
                save_json(self.state_path(task_id), state)

    @contextmanager
    def _state_file_lock(self, task_id: str) -> Iterator[None]:
        runtime = self.runtime_path(task_id)
        runtime.mkdir(parents=True, exist_ok=True)
        lock_path = runtime / ".state-write.lock"
        descriptor: int | None = None
        deadline = time.monotonic() + 10
        while descriptor is None:
            try:
                descriptor = os.open(
                    str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
            except FileExistsError:
                try:
                    if time.time() - lock_path.stat().st_mtime > 30:
                        lock_path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise TaskError(f"等待任务状态写锁超时: {task_id}")
                time.sleep(0.01)
        try:
            os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
            os.close(descriptor)
            descriptor = None
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def list_with_state(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for task in self.list_definitions():
            state = self.read_state(task["id"], reconcile=True)
            result.append({"task": task, "state": state})
        return result

    def control_dir(self, task_id: str) -> Path:
        return self.runtime_path(task_id) / "control"

    def enqueue_control(self, task_id: str, action: str, **values: Any) -> Path:
        self.load(task_id)
        control_dir = self.control_dir(task_id)
        control_dir.mkdir(parents=True, exist_ok=True)
        name = f"{time.time_ns():020d}-{uuid.uuid4().hex[:8]}.json"
        path = control_dir / name
        save_json(path, {"action": action, "created_at": now_iso(), **values})
        return path

    def pop_controls(self, task_id: str) -> list[dict[str, Any]]:
        control_dir = self.control_dir(task_id)
        if not control_dir.exists():
            return []
        controls: list[dict[str, Any]] = []
        for path in sorted(control_dir.glob("*.json")):
            value = load_json(path)
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            if isinstance(value, dict):
                controls.append(value)
        return controls

    def clear_controls(self, task_id: str) -> None:
        control_dir = self.control_dir(task_id)
        if not control_dir.exists():
            return
        for path in control_dir.glob("*.json"):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    @contextmanager
    def start_lock(self, task_id: str) -> Iterator[None]:
        runtime = self.runtime_path(task_id)
        runtime.mkdir(parents=True, exist_ok=True)
        lock_path = runtime / "start.lock"
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            try:
                owner_pid = int(lock_path.read_text(encoding="ascii").strip())
                age = time.time() - lock_path.stat().st_mtime
            except (OSError, ValueError):
                owner_pid = 0
                age = 31
            if process_matches(owner_pid) and age <= 30:
                raise TaskError("另一个启动操作正在进行") from exc
            try:
                lock_path.unlink()
                descriptor = os.open(
                    str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
            except OSError as retry_exc:
                raise TaskError("无法清理过期的任务启动锁") from retry_exc
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            yield
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def delete(self, task_id: str, *, purge_runtime: bool = False) -> None:
        state = self.read_state(task_id, reconcile=True)
        if state["status"] in ACTIVE_STATUSES:
            raise TaskError("请先停止任务，再删除任务")
        path = self.definition_path(task_id)
        if not path.exists():
            raise TaskError(f"任务不存在: {task_id}")
        path.unlink()
        if purge_runtime:
            runtime = self.runtime_path(task_id).resolve()
            parent = self.task_runtime_dir.resolve()
            if runtime.parent != parent:
                raise TaskError("拒绝清理超出任务运行目录的路径")
            shutil.rmtree(runtime, ignore_errors=True)
