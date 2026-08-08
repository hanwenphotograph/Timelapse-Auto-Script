"""Validate the private commands required by a task before it starts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from timelapse_manager.bracketlapse import detect_bracketlapse
from timelapse_manager.dependency_manager.health import (
    probe_command,
    tool_probe_arguments,
)
from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.errors import ConfigError
from timelapse_manager.process_utils import resolve_command


@dataclass(frozen=True)
class RuntimeCommands:
    camera: tuple[str, ...]
    bracketlapse: tuple[str, ...] = ()


def resolve_runtime_commands(
    root: Path,
    commands: dict[str, Any],
    *,
    processing_enabled: bool,
) -> RuntimeCommands:
    paths = DependencyPaths.discover(root)
    environment = paths.runtime_environment()
    camera = resolve_command(str(commands["camera"]), root=root)
    camera_probe = probe_command(camera, env=environment)
    if not camera_probe.ready:
        raise ConfigError(f"Camera Timelapse Controller 不可用：{camera_probe.detail}")
    _require_private_tool("gphoto2", root, environment)
    if not processing_enabled:
        return RuntimeCommands(tuple(camera))
    bracket = detect_bracketlapse(
        str(commands["bracketlapse"]),
        str(commands.get("bracketlapse_fallback") or "") or None,
        root=root,
        env=environment,
    )
    if not bracket.enabled:
        raise ConfigError(f"Bracketlapse 不可用：{bracket.reason}")
    for name in ("enfuse", "ffmpeg", "simple-deflicker"):
        _require_private_tool(name, root, environment)
    return RuntimeCommands(tuple(camera), bracket.command)


def _require_private_tool(
    name: str,
    root: Path,
    environment: dict[str, str],
) -> None:
    try:
        command = resolve_command(name, root=root)
    except Exception as exc:
        raise ConfigError(f"任务依赖 {name} 不可用：{exc}") from exc
    probe = probe_command(
        command,
        tool_probe_arguments(name),
        env=environment,
    )
    if not probe.ready:
        raise ConfigError(f"任务依赖 {name} 不可用：{probe.detail}")
