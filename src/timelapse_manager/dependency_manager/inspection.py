"""Inspect configured workflow commands and their child dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from timelapse_manager.bracketlapse import detect_bracketlapse
from timelapse_manager.dependency_manager.build_info import inspect_build_info
from timelapse_manager.dependency_manager.catalog import CATALOG, CATALOG_BY_ID
from timelapse_manager.dependency_manager.models import (
    DependencyBuildInfo,
    DependencyStatus,
)
from timelapse_manager.dependency_manager.sunset_resources import (
    inspect_sunset_resources,
)
from timelapse_manager.process_utils import resolve_command
from timelapse_manager.sunset_score.availability import (
    SunsetScoreAvailability,
    detect_sunset_score,
)


class DependencyInspector:
    def inspect(
        self,
        commands: dict[str, Any],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[DependencyStatus]:
        camera = str(commands.get("camera", "camera-timelapse"))
        bracket = str(commands.get("bracketlapse", "brackerlapse"))
        bracket_fallback = str(commands.get("bracketlapse_fallback", "bracketlapse"))
        sunset = str(commands.get("sunsetscore", "sunsetscore"))
        sunset_availability = detect_sunset_score(sunset)
        checks = (
            ("camera", lambda: self._owned_command(camera)),
            ("gphoto2", lambda: self._command("gphoto2")),
            (
                "bracketlapse",
                lambda: self._bracketlapse(bracket, bracket_fallback),
            ),
            ("enfuse", lambda: self._command("enfuse")),
            ("ffmpeg", lambda: self._command("ffmpeg")),
            ("align_image_stack", lambda: self._command("align_image_stack")),
            ("sunsetscore", lambda: self._sunset_score(sunset_availability)),
        )
        raw: dict[str, tuple[str, str, DependencyBuildInfo | None]] = {}
        total = len(CATALOG)
        for completed, (identifier, operation) in enumerate(checks, start=1):
            raw[identifier] = operation()
            _report(on_progress, completed, total, identifier)
        resources = inspect_sunset_resources(sunset_availability)
        for completed, identifier in enumerate(resources, start=len(checks) + 1):
            state, detail = resources[identifier]
            raw[identifier] = state, detail, None
            _report(on_progress, completed, total, identifier)
        return [
            DependencyStatus(
                spec,
                raw[spec.identifier][0],
                raw[spec.identifier][1],
                raw[spec.identifier][2],
            )
            for spec in CATALOG
        ]

    @staticmethod
    def _command(
        primary: str, fallback: str | None = None
    ) -> tuple[str, str, None]:
        try:
            command = resolve_command(primary, fallback)
        except Exception as exc:
            return "missing", str(exc), None
        return "ready", command[0], None

    @staticmethod
    def _owned_command(primary: str) -> tuple[str, str, DependencyBuildInfo | None]:
        try:
            command = resolve_command(primary)
        except Exception as exc:
            return "missing", str(exc), None
        return "ready", command[0], inspect_build_info(command)

    @staticmethod
    def _sunset_score(
        result: SunsetScoreAvailability,
    ) -> tuple[str, str, DependencyBuildInfo | None]:
        if result.enabled:
            build_info = _matching_build_info(result.command, result.version)
            return "ready", result.command[0], build_info
        if result.command:
            state = "outdated" if "低于最低要求" in result.reason else "issue"
            return state, result.reason, None
        return "missing", result.reason, None

    @staticmethod
    def _bracketlapse(
        primary: str, fallback: str
    ) -> tuple[str, str, DependencyBuildInfo | None]:
        result = detect_bracketlapse(primary, fallback or None)
        if result.enabled:
            build_info = _matching_build_info(result.command, result.version)
            return "ready", result.command[0], build_info
        if result.command:
            state = "outdated" if "低于最低要求" in result.reason else "issue"
            return state, result.reason, None
        return "missing", result.reason, None


def _matching_build_info(
    command: tuple[str, ...], version: str | None
) -> DependencyBuildInfo | None:
    build_info = inspect_build_info(command)
    if build_info is not None and build_info.version == version:
        return build_info
    if version is not None:
        return DependencyBuildInfo(version)
    return None


def _report(
    callback: Callable[[int, int, str], None] | None,
    completed: int,
    total: int,
    identifier: str,
) -> None:
    if callback:
        callback(completed, total, CATALOG_BY_ID[identifier].name)
