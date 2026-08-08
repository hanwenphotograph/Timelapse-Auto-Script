"""Discover a Bracketlapse CLI with the incremental event protocol."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable

from timelapse_manager.process_utils import resolve_command


MINIMUM_VERSION = (0, 2, 0)
MINIMUM_VERSION_TEXT = ".".join(str(part) for part in MINIMUM_VERSION)
VERSION_PATTERN = re.compile(
    r"^\s*bracketlapse\s+(\d+)\.(\d+)\.(\d+)(?:\S*)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class BracketlapseAvailability:
    command: tuple[str, ...] = ()
    version: str | None = None
    reason: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.command and self.version)


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def detect_bracketlapse(
    primary: str,
    fallback: str | None = None,
    *,
    timeout: float = 10,
    run: RunCommand = subprocess.run,
) -> BracketlapseAvailability:
    try:
        command = resolve_command(primary, fallback)
    except Exception as exc:
        return BracketlapseAvailability(reason=f"未找到命令：{exc}")
    try:
        completed = run(
            [*command, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return BracketlapseAvailability(
            command=tuple(command), reason=f"版本探测超过 {timeout:g} 秒"
        )
    except OSError as exc:
        return BracketlapseAvailability(
            command=tuple(command), reason=f"版本探测失败：{exc}"
        )
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part
    )
    if completed.returncode != 0:
        return BracketlapseAvailability(
            command=tuple(command),
            reason=f"版本探测失败：{output or completed.returncode}",
        )
    match = VERSION_PATTERN.search(output)
    if not match:
        return BracketlapseAvailability(
            command=tuple(command), reason=f"无法解析版本：{output or '无输出'}"
        )
    version_tuple = tuple(int(part) for part in match.groups())
    version = ".".join(match.groups())
    if version_tuple < MINIMUM_VERSION:
        return BracketlapseAvailability(
            command=tuple(command),
            reason=f"版本 {version} 低于最低要求 {MINIMUM_VERSION_TEXT}",
        )
    return BracketlapseAvailability(tuple(command), version)
