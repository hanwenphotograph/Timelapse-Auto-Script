"""Small, cross-platform persistence helpers."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from timelapse_manager.errors import ConfigError


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def deep_merge(defaults: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, default in defaults.items():
        value = values.get(key)
        if isinstance(default, dict) and isinstance(value, dict):
            merged[key] = deep_merge(default, value)
        elif key in values and value is not None:
            merged[key] = value
        else:
            merged[key] = default
    for key, value in values.items():
        if key not in merged:
            merged[key] = value
    return merged


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = yaml.safe_load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {path}") from exc
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"读取 YAML 失败 {path}: {exc}") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"YAML 顶层必须是映射: {path}")
    return value


def parse_yaml(text: str, label: str = "YAML") -> dict[str, Any]:
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{label} 语法错误: {exc}") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{label} 顶层必须是映射")
    return value


def yaml_text(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        last_error: PermissionError | None = None
        for attempt in range(50):
            try:
                os.replace(temp_name, path)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(min(0.005 * (attempt + 1), 0.1))
        if last_error is not None:
            raise last_error
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    _atomic_write(path, yaml_text(data))


def load_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data: Any) -> None:
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
