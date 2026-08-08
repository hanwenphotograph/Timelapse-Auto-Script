"""Inspect configured workflow commands and their child dependencies."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from timelapse_manager.bracketlapse import detect_bracketlapse
from timelapse_manager.dependency_manager.build_info import (
    inspect_build_info,
    matching_build_info,
)
from timelapse_manager.dependency_manager.catalog import CATALOG, report_progress
from timelapse_manager.dependency_manager.health import (
    probe_command,
    tool_probe_arguments,
)
from timelapse_manager.dependency_manager.models import (
    DependencyBuildInfo,
    DependencyStatus,
)
from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.dependency_manager.sources import (
    SOURCE_REPOSITORIES,
    attach_source_branches,
    inspect_remote_branches,
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
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.paths = DependencyPaths.discover(self.root)
        self.environment = self.paths.runtime_environment()

    def inspect(
        self,
        commands: dict[str, Any],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[DependencyStatus]:
        camera = str(commands.get("camera", "camera-timelapse"))
        bracket = str(commands.get("bracketlapse", "brackerlapse"))
        bracket_fallback = str(commands.get("bracketlapse_fallback", "bracketlapse"))
        sunset = str(commands.get("sunsetscore", "sunsetscore"))
        with ThreadPoolExecutor(max_workers=len(SOURCE_REPOSITORIES)) as executor:
            branch_futures = {
                identifier: executor.submit(inspect_remote_branches, identifier)
                for identifier in SOURCE_REPOSITORIES
            }
            raw = self._inspect_dependencies(
                camera,
                bracket,
                bracket_fallback,
                sunset,
                on_progress,
            )
            branches = {
                identifier: future.result()
                for identifier, future in branch_futures.items()
            }
        statuses = [
            DependencyStatus(
                spec,
                raw[spec.identifier][0],
                raw[spec.identifier][1],
                raw[spec.identifier][2],
            )
            for spec in CATALOG
        ]
        return [attach_source_branches(status, branches) for status in statuses]

    def _inspect_dependencies(
        self,
        camera: str,
        bracket: str,
        bracket_fallback: str,
        sunset: str,
        on_progress: Callable[[int, int, str], None] | None,
    ) -> dict[str, tuple[str, str, DependencyBuildInfo | None]]:
        sunset_availability = detect_sunset_score(
            sunset,
            root=self.root,
            env=self.environment,
        )
        checks = (
            ("camera", lambda: self._owned_command(camera)),
            ("gphoto2", lambda: self._command("gphoto2")),
            (
                "bracketlapse",
                lambda: self._bracketlapse(bracket, bracket_fallback),
            ),
            ("enfuse", lambda: self._command("enfuse")),
            ("ffmpeg", lambda: self._command("ffmpeg")),
            ("simple_deflicker", lambda: self._command("simple-deflicker")),
            ("align_image_stack", lambda: self._command("align_image_stack")),
            ("sunsetscore", lambda: self._sunset_score(sunset_availability)),
        )
        raw: dict[str, tuple[str, str, DependencyBuildInfo | None]] = {}
        total = len(CATALOG)
        for completed, (identifier, operation) in enumerate(checks, start=1):
            raw[identifier] = operation()
            report_progress(on_progress, completed, total, identifier)
        resources = inspect_sunset_resources(
            sunset_availability,
            root=self.root,
            env=self.environment,
        )
        for completed, identifier in enumerate(resources, start=len(checks) + 1):
            state, detail = resources[identifier]
            raw[identifier] = state, detail, None
            report_progress(on_progress, completed, total, identifier)
        return raw

    def _command(
        self, primary: str, fallback: str | None = None
    ) -> tuple[str, str, None]:
        try:
            command = resolve_command(primary, fallback, root=self.root)
        except Exception as exc:
            return "missing", str(exc), None
        probe = probe_command(
            command,
            tool_probe_arguments(primary),
            env=self.environment,
        )
        if not probe.ready:
            return "issue", f"{command[0]}：{probe.detail}", None
        return "ready", command[0], None

    def _owned_command(
        self, primary: str
    ) -> tuple[str, str, DependencyBuildInfo | None]:
        try:
            command = resolve_command(primary, root=self.root)
        except Exception as exc:
            return "missing", str(exc), None
        probe = probe_command(command, env=self.environment)
        if not probe.ready:
            return "issue", f"{command[0]}：{probe.detail}", None
        return (
            "ready",
            command[0],
            inspect_build_info(
                command,
                env=self.environment,
            ),
        )

    def _sunset_score(
        self,
        result: SunsetScoreAvailability,
    ) -> tuple[str, str, DependencyBuildInfo | None]:
        if result.enabled:
            build_info = matching_build_info(
                result.command,
                result.version,
                env=self.environment,
            )
            return "ready", result.command[0], build_info
        if result.command:
            state = "outdated" if "低于最低要求" in result.reason else "issue"
            return state, result.reason, None
        return "missing", result.reason, None

    def _bracketlapse(
        self, primary: str, fallback: str
    ) -> tuple[str, str, DependencyBuildInfo | None]:
        result = detect_bracketlapse(
            primary,
            fallback or None,
            root=self.root,
            env=self.environment,
        )
        if result.enabled:
            build_info = matching_build_info(
                result.command,
                result.version,
                env=self.environment,
            )
            return "ready", result.command[0], build_info
        if result.command:
            state = "outdated" if "低于最低要求" in result.reason else "issue"
            return state, result.reason, None
        return "missing", result.reason, None
