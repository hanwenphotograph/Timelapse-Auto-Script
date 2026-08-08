"""Discover a compatible external SunsetScore command."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from timelapse_manager.process_utils import resolve_command


MINIMUM_VERSION = (0, 10, 0)
MINIMUM_VERSION_TEXT = ".".join(str(part) for part in MINIMUM_VERSION)
VERSION_PATTERN = re.compile(
    r"^\s*sunsetscore\s+(\d+)\.(\d+)\.(\d+)(?:\S*)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class SunsetScoreAvailability:
    command: tuple[str, ...] = ()
    version: str | None = None
    reason: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.command and self.version)


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def detect_sunset_score(
    command_value: str,
    *,
    timeout: float = 10,
    run: RunCommand = subprocess.run,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> SunsetScoreAvailability:
    try:
        command = resolve_command(command_value, root=root)
    except Exception as exc:
        return SunsetScoreAvailability(reason=f"未找到命令：{exc}")

    try:
        completed = run(
            [*command, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=dict(env) if env is not None else None,
        )
    except subprocess.TimeoutExpired:
        return SunsetScoreAvailability(
            command=tuple(command), reason=f"版本探测超过 {timeout:g} 秒"
        )
    except OSError as exc:
        return SunsetScoreAvailability(
            command=tuple(command), reason=f"版本探测失败：{exc}"
        )

    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part
    )
    if completed.returncode != 0:
        detail = output or f"退出码 {completed.returncode}"
        return SunsetScoreAvailability(
            command=tuple(command), reason=f"版本探测失败：{detail}"
        )
    match = VERSION_PATTERN.search(output)
    if not match:
        return SunsetScoreAvailability(
            command=tuple(command), reason=f"无法解析版本：{output or '无输出'}"
        )
    version_tuple = tuple(int(part) for part in match.groups())
    version = ".".join(match.groups())
    if version_tuple < MINIMUM_VERSION:
        return SunsetScoreAvailability(
            command=tuple(command),
            version=None,
            reason=f"版本 {version} 低于最低要求 {MINIMUM_VERSION_TEXT}",
        )
    return SunsetScoreAvailability(command=tuple(command), version=version)
