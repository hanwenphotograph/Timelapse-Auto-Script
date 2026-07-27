"""Shared dependency catalog and inspection models."""

from __future__ import annotations

from dataclasses import dataclass
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
class DependencyStatus:
    spec: DependencySpec
    state: DependencyState
    detail: str
    action_available: bool = False

    @property
    def ready(self) -> bool:
        return self.state == "ready"
