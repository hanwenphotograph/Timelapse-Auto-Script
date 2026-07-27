"""Dependency discovery and installation used by the package-management UI."""

from timelapse_manager.dependency_manager.manager import DependencyManager
from timelapse_manager.dependency_manager.models import DependencyStatus

__all__ = ["DependencyManager", "DependencyStatus"]
