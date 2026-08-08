"""Shared dependency catalog and inspection models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


DependencyState = Literal["ready", "missing", "issue", "outdated", "checking"]


@dataclass(frozen=True)
class DependencySpec:
    identifier: str
    group: str
    parent_id: str | None
    name: str
    description: str
    required: bool
    action_id: str | None = None
    action_label: str = "快速安装"


@dataclass(frozen=True)
class DependencyBuildInfo:
    version: str
    branch: str | None = None
    build_time: str | None = None
    commit: str | None = None

    @property
    def summary(self) -> str:
        parts = [f"版本 {_compact(self.version, 24)}"]
        if self.branch:
            parts.append(f"分支 {_compact(self.branch, 32)}")
        if self.build_time:
            parts.append(f"构建 {_format_build_time(self.build_time)}")
        return " · ".join(parts)


@dataclass(frozen=True)
class DependencyStatus:
    spec: DependencySpec
    state: DependencyState
    detail: str
    build_info: DependencyBuildInfo | None = None
    action_available: bool = False

    @property
    def ready(self) -> bool:
        return self.state == "ready"


def _format_build_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _compact(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."
