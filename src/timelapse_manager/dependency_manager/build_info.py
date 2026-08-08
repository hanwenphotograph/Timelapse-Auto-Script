"""Consume public build metadata exposed by owned CLI dependencies."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
import json
import subprocess
from typing import Any

from timelapse_manager.dependency_manager.models import DependencyBuildInfo


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def inspect_build_info(
    command: Sequence[str],
    *,
    timeout: float = 5.0,
    run: RunCommand = subprocess.run,
    env: Mapping[str, str] | None = None,
) -> DependencyBuildInfo | None:
    try:
        completed = run(
            [*command, "--build-info"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=dict(env) if env is not None else None,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        document = json.loads(completed.stdout)
        return _parse_document(document)
    except (json.JSONDecodeError, ValueError):
        return None


def matching_build_info(
    command: Sequence[str],
    version: str | None,
    *,
    env: Mapping[str, str] | None = None,
) -> DependencyBuildInfo | None:
    build_info = inspect_build_info(command, env=env)
    if build_info is not None and build_info.version == version:
        return build_info
    return DependencyBuildInfo(version) if version is not None else None


def _parse_document(value: Any) -> DependencyBuildInfo:
    if not isinstance(value, dict):
        raise ValueError("构建信息必须是 JSON 对象")
    version = _required_text(value.get("version"), "version")
    branch = _optional_text(value.get("branch"), "branch")
    commit = _optional_text(value.get("commit"), "commit")
    build_time = _optional_text(value.get("build_time"), "build_time")
    if build_time is not None:
        parsed = datetime.fromisoformat(build_time.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("build_time 必须包含时区")
    return DependencyBuildInfo(version, branch, build_time, commit)


def _required_text(value: Any, name: str) -> str:
    result = _optional_text(value, name)
    if result is None:
        raise ValueError(f"{name} 必须是非空字符串")
    return result


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串或 null")
    return value.strip()
