"""Task definition defaults and validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from timelapse_manager.errors import ConfigError
from timelapse_manager.io_utils import deep_merge


PRESET_DESCRIPTIONS = {
    "scheduled_once": "生成下一个清晨或黄昏时段的单次手动任务",
    "scheduled_loop": "生成清晨/黄昏手动任务并在每轮结束后自动接力",
    "eternal": "持续拍摄，按完整曝光组分批归档并串行处理",
    "manual": "手动指定日期、时段和工作目录的单次任务",
}

PERSISTED_PRESETS = {"manual", "eternal", "scheduled_once", "scheduled_loop"}
LEGACY_SCHEDULED_PRESETS = {"scheduled_once", "scheduled_loop"}
SCHEMA_VERSION = 2

BASE_TASK: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "id": "",
    "name": "",
    "preset": "manual",
    "created_at": "",
    "capture": {},
    "processing": {"enabled": True},
    "cleanup": {
        "enabled": False,
        "keep_directories": ["hdr_enfuse", "hdr_video"],
        "delete_incomplete_groups": False,
        "on_failure": False,
    },
    "retry": {"enabled": False},
    "environment": {},
}


def normalize_task(raw: dict[str, Any]) -> dict[str, Any]:
    defaults = deepcopy(BASE_TASK)
    if raw.get("preset") == "eternal":
        defaults["capture"] = {"interval_seconds": None}
        defaults["cleanup"].update(
            {"enabled": True, "delete_incomplete_groups": True, "on_failure": True}
        )
        defaults["retry"] = {"enabled": True, "delay_seconds": None}
        defaults["eternal"] = {
            "batch_groups": None,
            "images_per_group": None,
            "state_dir": None,
        }
    return deep_merge(defaults, raw)


def _optional_number(
    data: dict[str, Any], key: str, label: str, minimum: float
) -> None:
    value = data.get(key)
    if value is not None and (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value < minimum
    ):
        raise ConfigError(f"{label} 必须为空或大于等于 {minimum:g}")


def _validate_continuation(task: dict[str, Any]) -> None:
    continuation = task.get("continuation")
    if continuation is None:
        return
    if task["preset"] != "manual" or not isinstance(continuation, dict):
        raise ConfigError("continuation 只能用于 Manual 任务且必须是映射")
    for key in ("chain_id", "chain_name", "source_preset"):
        if not isinstance(continuation.get(key), str) or not continuation[key].strip():
            raise ConfigError(f"continuation.{key} 不能为空")
    if continuation["source_preset"] != "scheduled_loop":
        raise ConfigError("continuation.source_preset 必须是 scheduled_loop")
    if not isinstance(continuation.get("enabled"), bool):
        raise ConfigError("continuation.enabled 必须是 true 或 false")
    sequence = continuation.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ConfigError("continuation.sequence 必须是正整数")
    previous = continuation.get("previous_task_id")
    if previous is not None and (
        not isinstance(previous, str) or not previous.strip()
    ):
        raise ConfigError("continuation.previous_task_id 必须是非空任务 ID")


def validate_task(task: dict[str, Any], *, for_start: bool = False) -> None:
    if task.get("schema_version") not in {1, SCHEMA_VERSION}:
        raise ConfigError("不支持的任务 schema_version")
    for key in ("id", "name", "preset"):
        if not isinstance(task.get(key), str) or not task[key].strip():
            raise ConfigError(f"任务字段 {key} 不能为空")
    if task["preset"] not in PERSISTED_PRESETS:
        raise ConfigError(f"未知任务执行模式: {task['preset']}")
    for key in ("capture", "processing", "cleanup", "retry", "environment"):
        if not isinstance(task.get(key), dict):
            raise ConfigError(f"任务 {key} 必须是映射")

    capture = task["capture"]
    _optional_number(capture, "interval_seconds", "capture.interval_seconds", 0.01)
    if not isinstance(task["processing"].get("enabled"), bool):
        raise ConfigError("processing.enabled 必须是 true 或 false")
    if task["preset"] == "manual" and for_start:
        required = ("work_dir", "start_date", "start_at", "end_date", "end_at")
        missing = [key for key in required if not capture.get(key)]
        if missing:
            raise ConfigError(
                "手动任务开始前必须设置: "
                + ", ".join(f"capture.{key}" for key in missing)
            )

    cleanup = task["cleanup"]
    for key in ("enabled", "delete_incomplete_groups", "on_failure"):
        if not isinstance(cleanup.get(key), bool):
            raise ConfigError(f"cleanup.{key} 必须是 true 或 false")
    keep = cleanup.get("keep_directories")
    if not isinstance(keep, list) or not all(
        isinstance(item, str) and item for item in keep
    ):
        raise ConfigError("cleanup.keep_directories 必须是非空字符串列表")

    retry = task["retry"]
    if not isinstance(retry.get("enabled"), bool):
        raise ConfigError("retry.enabled 必须是 true 或 false")
    _optional_number(retry, "delay_seconds", "retry.delay_seconds", 0)
    _validate_continuation(task)

    if task["preset"] == "eternal":
        eternal = task.get("eternal")
        if not isinstance(eternal, dict):
            raise ConfigError("eternal 任务必须包含 eternal 映射")
        for key in ("batch_groups", "images_per_group"):
            value = eternal.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ConfigError(f"eternal.{key} 必须为空或为正整数")
        state_dir = eternal.get("state_dir")
        if state_dir is not None and (
            not isinstance(state_dir, str) or not state_dir.strip()
        ):
            raise ConfigError("eternal.state_dir 必须为空或为非空路径")

    if not all(
        isinstance(key, str) and isinstance(value, (str, int, float, bool))
        for key, value in task["environment"].items()
    ):
        raise ConfigError("environment 的键必须是字符串，值必须是标量")
