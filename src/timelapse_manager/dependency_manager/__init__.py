"""Dependency discovery and installation used by the package-management UI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from timelapse_manager.dependency_manager.manager import DependencyManager
    from timelapse_manager.dependency_manager.models import DependencyStatus

__all__ = ["DependencyManager", "DependencyStatus"]


def __getattr__(name: str) -> Any:
    if name == "DependencyManager":
        from timelapse_manager.dependency_manager.manager import DependencyManager

        return DependencyManager
    if name == "DependencyStatus":
        from timelapse_manager.dependency_manager.models import DependencyStatus

        return DependencyStatus
    raise AttributeError(name)
