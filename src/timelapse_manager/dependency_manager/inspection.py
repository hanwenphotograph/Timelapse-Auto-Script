"""Inspect configured workflow commands and their child dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from timelapse_manager.bracketlapse import detect_bracketlapse
from timelapse_manager.dependency_manager.catalog import CATALOG, CATALOG_BY_ID
from timelapse_manager.dependency_manager.models import DependencyStatus
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
            ("camera", lambda: self._command(camera)),
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
        raw: dict[str, tuple[str, str]] = {}
        total = len(CATALOG)
        for completed, (identifier, operation) in enumerate(checks, start=1):
            raw[identifier] = operation()
            _report(on_progress, completed, total, identifier)
        resources = inspect_sunset_resources(sunset_availability)
        for completed, identifier in enumerate(resources, start=len(checks) + 1):
            raw[identifier] = resources[identifier]
            _report(on_progress, completed, total, identifier)
        return [
            DependencyStatus(spec, raw[spec.identifier][0], raw[spec.identifier][1])
            for spec in CATALOG
        ]

    @staticmethod
    def _command(primary: str, fallback: str | None = None) -> tuple[str, str]:
        try:
            command = resolve_command(primary, fallback)
        except Exception as exc:
            return "missing", str(exc)
        return "ready", command[0]

    @staticmethod
    def _sunset_score(result: SunsetScoreAvailability) -> tuple[str, str]:
        if result.enabled:
            return "ready", f"版本 {result.version} · {result.command[0]}"
        if result.command:
            state = "outdated" if "低于最低要求" in result.reason else "issue"
            return state, result.reason
        return "missing", result.reason

    @staticmethod
    def _bracketlapse(primary: str, fallback: str) -> tuple[str, str]:
        result = detect_bracketlapse(primary, fallback or None)
        if result.enabled:
            return "ready", f"版本 {result.version} · {result.command[0]}"
        if result.command:
            state = "outdated" if "低于最低要求" in result.reason else "issue"
            return state, result.reason
        return "missing", result.reason


def _report(
    callback: Callable[[int, int, str], None] | None,
    completed: int,
    total: int,
    identifier: str,
) -> None:
    if callback:
        callback(completed, total, CATALOG_BY_ID[identifier].name)
