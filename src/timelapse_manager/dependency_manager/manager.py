"""Facade used by the GUI to inspect and install workflow dependencies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from timelapse_manager.dependency_manager.catalog import CATALOG, CATALOG_BY_ID
from timelapse_manager.dependency_manager.inspection import DependencyInspector
from timelapse_manager.dependency_manager.installation import (
    DependencyInstallError,
    DependencyInstaller,
)
from timelapse_manager.dependency_manager.models import DependencyStatus


class DependencyManager:
    def __init__(
        self,
        root: Path,
        commands: Callable[[], dict[str, Any]],
    ) -> None:
        self._commands = commands
        self._inspector = DependencyInspector(root)
        self._installer = DependencyInstaller(root)

    @property
    def dependency_root(self) -> Path:
        return self._installer.paths.root

    def placeholders(self) -> list[DependencyStatus]:
        return [DependencyStatus(spec, "checking", "等待检测") for spec in CATALOG]

    def inspect(
        self,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[DependencyStatus]:
        commands = dict(self._commands())
        statuses = self._inspector.inspect(commands, on_progress)
        return [
            replace(
                status,
                action_available=bool(
                    status.spec.action_id
                    and self._installer.plan(status.spec.action_id, commands)
                ),
            )
            for status in statuses
        ]

    def confirmation(self, identifier: str, branch: str | None = None) -> str | None:
        spec = CATALOG_BY_ID.get(identifier)
        if not spec or not spec.action_id:
            return None
        plan = self._installer.plan(
            spec.action_id,
            dict(self._commands()),
            branch=branch,
        )
        return plan.confirmation if plan else None

    def install(
        self,
        identifier: str,
        on_output: Callable[[str], None] | None = None,
        on_progress: Callable[[float], None] | None = None,
        *,
        branch: str | None = None,
    ) -> None:
        spec = CATALOG_BY_ID.get(identifier)
        if not spec or not spec.action_id:
            raise DependencyInstallError("该依赖没有可用的快速安装操作")
        plan = self._installer.plan(
            spec.action_id,
            dict(self._commands()),
            branch=branch,
        )
        if not plan:
            raise DependencyInstallError("当前平台没有可用的自动安装方案")
        self._installer.execute(plan, on_output, on_progress)
