"""Project and webhook YAML configuration."""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from timelapse_manager.errors import ConfigError
from timelapse_manager.io_utils import (
    deep_merge,
    load_yaml,
    parse_yaml,
    save_yaml,
    yaml_text,
)
from timelapse_manager.paths import AppPaths
from timelapse_manager.schedule import validate_schedule


DEFAULT_PROJECT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "auto_root": str(Path.home() / "Pictures" / "AutoTimelapse"),
    "capture_interval_seconds": 6,
    "watch_quiet_seconds": 60,
    "disk_space_warning_threshold_gb": 0,
    "morning": {"start_at": "03:00", "end_at": "09:00"},
    "dusk": {"start_at": "16:00", "end_at": "20:00"},
    "commands": {
        "camera": "camera-timelapse",
        "bracketlapse": "brackerlapse",
        "bracketlapse_fallback": "bracketlapse",
    },
    "runtime": {
        "state_dir": ".timelapse",
        "tasks_dir": "config/tasks",
        "poll_interval_seconds": 0.25,
        "startup_probe_seconds": 2,
        "stop_timeout_seconds": 10,
        "retry_delay_seconds": 300,
        "task_history_retention_days": 30,
    },
    "eternal": {
        "batch_groups": 2000,
        "images_per_group": 3,
        "queue_poll_seconds": 2,
        "archive_retry_seconds": 60,
    },
}

DEFAULT_WEBHOOK_CONFIG: dict[str, Any] = {
    "enabled": False,
    "url": "",
    "body": '{"content":"__CONTENT__","time":"__TIME__"}',
    "push_image": False,
    "image_body": '{"content":"__CONTENT__","image":"__IMGBASE64__","md5":"__IMGMD5__"}',
}


def _number(
    data: dict[str, Any], key: str, minimum: float, *, integer: bool = False
) -> None:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} 必须是数字")
    if value < minimum:
        raise ConfigError(f"{key} 不能小于 {minimum}")
    if integer and not isinstance(value, int):
        raise ConfigError(f"{key} 必须是整数")


def validate_project_config(data: dict[str, Any]) -> None:
    if not isinstance(data.get("auto_root"), str) or not data["auto_root"].strip():
        raise ConfigError("auto_root 不能为空")
    _number(data, "capture_interval_seconds", 0.01)
    _number(data, "watch_quiet_seconds", 0)
    _number(data, "disk_space_warning_threshold_gb", 0)
    morning = data.get("morning")
    dusk = data.get("dusk")
    if not isinstance(morning, dict) or not isinstance(dusk, dict):
        raise ConfigError("morning 和 dusk 必须是映射")
    validate_schedule(morning, dusk)

    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise ConfigError("commands 必须是映射")
    for key in ("camera", "bracketlapse"):
        if not isinstance(commands.get(key), str) or not commands[key].strip():
            raise ConfigError(f"commands.{key} 不能为空")

    runtime = data.get("runtime")
    if not isinstance(runtime, dict):
        raise ConfigError("runtime 必须是映射")
    for key in ("state_dir", "tasks_dir"):
        if not isinstance(runtime.get(key), str) or not runtime[key].strip():
            raise ConfigError(f"runtime.{key} 不能为空")
    _number(runtime, "poll_interval_seconds", 0.05)
    _number(runtime, "startup_probe_seconds", 0)
    _number(runtime, "stop_timeout_seconds", 0.1)
    _number(runtime, "retry_delay_seconds", 0)
    _number(runtime, "task_history_retention_days", 1, integer=True)

    eternal = data.get("eternal")
    if not isinstance(eternal, dict):
        raise ConfigError("eternal 必须是映射")
    _number(eternal, "batch_groups", 1, integer=True)
    _number(eternal, "images_per_group", 1, integer=True)
    _number(eternal, "queue_poll_seconds", 0.1)
    _number(eternal, "archive_retry_seconds", 0)


def validate_webhook_config(data: dict[str, Any]) -> None:
    for key in ("enabled", "push_image"):
        if not isinstance(data.get(key), bool):
            raise ConfigError(f"webhook.{key} 必须是 true 或 false")
    if not data["enabled"]:
        return
    if not isinstance(data.get("url"), str) or not data["url"].strip():
        raise ConfigError("webhook 已开启，但 url 为空")
    if "__CONTENT__" not in str(data.get("body", "")):
        raise ConfigError("webhook body 必须包含 __CONTENT__")
    if data["push_image"]:
        image_body = str(data.get("image_body", ""))
        for token in ("__IMGBASE64__", "__IMGMD5__"):
            if token not in image_body:
                raise ConfigError(f"webhook image_body 必须包含 {token}")


@dataclass(frozen=True)
class LoadedConfig:
    project: dict[str, Any]
    webhook: dict[str, Any]
    paths: AppPaths

    @property
    def auto_root(self) -> Path:
        return self.paths.resolve_from_root(self.project["auto_root"])

    @property
    def runtime_dir(self) -> Path:
        return self.paths.resolve_from_root(self.project["runtime"]["state_dir"])

    @property
    def tasks_dir(self) -> Path:
        return self.paths.resolve_from_root(self.project["runtime"]["tasks_dir"])


class ConfigManager:
    def __init__(self, paths: AppPaths | None = None):
        self.paths = paths or AppPaths.discover()

    def ensure(self) -> None:
        if not self.paths.config_file.exists():
            save_yaml(self.paths.config_file, deepcopy(DEFAULT_PROJECT_CONFIG))
        if not self.paths.webhook_file.exists():
            save_yaml(self.paths.webhook_file, deepcopy(DEFAULT_WEBHOOK_CONFIG))

    def load(self, *, create: bool = True) -> LoadedConfig:
        if create:
            self.ensure()
        project = deep_merge(DEFAULT_PROJECT_CONFIG, load_yaml(self.paths.config_file))
        webhook = deep_merge(DEFAULT_WEBHOOK_CONFIG, load_yaml(self.paths.webhook_file))
        self._apply_environment(project)
        validate_project_config(project)
        validate_webhook_config(webhook)
        return LoadedConfig(project, webhook, self.paths)

    @staticmethod
    def _apply_environment(project: dict[str, Any]) -> None:
        string_overrides = {
            "AUTO_ROOT": "auto_root",
            "AUTO_TIMELAPSE_ROOT": "auto_root",
            "MORNING_START_AT": ("morning", "start_at"),
            "MORNING_END_AT": ("morning", "end_at"),
            "DUSK_START_AT": ("dusk", "start_at"),
            "DUSK_END_AT": ("dusk", "end_at"),
        }
        for env_name, target in string_overrides.items():
            value = os.environ.get(env_name)
            if value is None:
                continue
            if isinstance(target, tuple):
                project[target[0]][target[1]] = value
            else:
                project[target] = value
        if "MORNING_START_AT" not in os.environ and os.environ.get("START_AT"):
            project["morning"]["start_at"] = os.environ["START_AT"]
        if "MORNING_END_AT" not in os.environ and os.environ.get("END_AT"):
            project["morning"]["end_at"] = os.environ["END_AT"]
        numeric_overrides = {
            "CAPTURE_INTERVAL_SECONDS": ("capture_interval_seconds", False),
            "WATCH_QUIET_SECONDS": ("watch_quiet_seconds", False),
            "DISK_SPACE_WARNING_THRESHOLD_GB": (
                "disk_space_warning_threshold_gb",
                False,
            ),
            "RETRY_DELAY_SECONDS": (("runtime", "retry_delay_seconds"), False),
            "ETERNAL_BATCH_GROUPS": (("eternal", "batch_groups"), True),
            "ETERNAL_QUEUE_POLL_SECONDS": (("eternal", "queue_poll_seconds"), False),
            "ETERNAL_ARCHIVE_RETRY_SECONDS": (
                ("eternal", "archive_retry_seconds"),
                False,
            ),
        }
        for env_name, (target, integer) in numeric_overrides.items():
            value = os.environ.get(env_name)
            if value is not None:
                try:
                    parsed: int | float = int(value) if integer else float(value)
                except ValueError as exc:
                    raise ConfigError(f"环境变量 {env_name} 必须是数字") from exc
                if isinstance(target, tuple):
                    project[target[0]][target[1]] = parsed
                else:
                    project[target] = parsed

    def read_text(self, kind: str) -> str:
        self.ensure()
        path = self._kind_path(kind)
        return path.read_text(encoding="utf-8")

    def validate_text(self, kind: str, text: str) -> dict[str, Any]:
        parsed = parse_yaml(text, f"{kind} YAML")
        if kind == "project":
            merged = deep_merge(DEFAULT_PROJECT_CONFIG, parsed)
            validate_project_config(merged)
        elif kind == "webhook":
            merged = deep_merge(DEFAULT_WEBHOOK_CONFIG, parsed)
            validate_webhook_config(merged)
        else:
            raise ConfigError(f"未知配置类型: {kind}")
        return parsed

    def save_text(self, kind: str, text: str) -> None:
        parsed = self.validate_text(kind, text)
        save_yaml(self._kind_path(kind), parsed)

    def normalized_text(self, kind: str) -> str:
        loaded = self.load()
        return yaml_text(loaded.project if kind == "project" else loaded.webhook)

    def _kind_path(self, kind: str) -> Path:
        if kind == "project":
            return self.paths.config_file
        if kind == "webhook":
            return self.paths.webhook_file
        raise ConfigError(f"未知配置类型: {kind}")
