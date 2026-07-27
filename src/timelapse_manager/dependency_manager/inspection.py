"""Inspect configured workflow commands and their child dependencies."""

from __future__ import annotations

from typing import Any

from timelapse_manager.dependency_manager.catalog import CATALOG
from timelapse_manager.dependency_manager.models import DependencyStatus
from timelapse_manager.dependency_manager.sunset_resources import (
    inspect_sunset_resources,
)
from timelapse_manager.process_utils import resolve_command
from timelapse_manager.sunset_score.availability import detect_sunset_score


class DependencyInspector:
    def inspect(self, commands: dict[str, Any]) -> list[DependencyStatus]:
        raw = {
            "camera": self._command(str(commands.get("camera", "camera-timelapse"))),
            "gphoto2": self._command("gphoto2"),
            "bracketlapse": self._command(
                str(commands.get("bracketlapse", "brackerlapse")),
                str(commands.get("bracketlapse_fallback", "bracketlapse")),
            ),
            "enfuse": self._command("enfuse"),
            "ffmpeg": self._command("ffmpeg"),
            "align_image_stack": self._command("align_image_stack"),
            "sunsetscore": self._sunset_score(
                str(commands.get("sunsetscore", "sunsetscore"))
            ),
            **inspect_sunset_resources(),
        }
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
    def _sunset_score(command_value: str) -> tuple[str, str]:
        result = detect_sunset_score(command_value)
        if result.enabled:
            return "ready", f"版本 {result.version} · {result.command[0]}"
        if result.command:
            state = "outdated" if "低于最低要求" in result.reason else "issue"
            return state, result.reason
        return "missing", result.reason
