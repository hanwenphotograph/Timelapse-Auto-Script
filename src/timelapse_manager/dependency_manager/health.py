"""Execute lightweight health probes for managed commands."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandProbe:
    ready: bool
    detail: str


TOOL_PROBE_ARGUMENTS = {
    "ffmpeg": ("-version",),
    "simple-deflicker": ("--help",),
    "align_image_stack": ("--help",),
}


def tool_probe_arguments(name: str) -> tuple[str, ...]:
    return TOOL_PROBE_ARGUMENTS.get(name, ("--version",))


def probe_command(
    command: Sequence[str],
    arguments: Sequence[str] = ("--version",),
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = 10,
) -> CommandProbe:
    try:
        completed = subprocess.run(
            [*command, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=dict(env) if env is not None else None,
        )
    except subprocess.TimeoutExpired:
        return CommandProbe(False, f"健康检查超过 {timeout:g} 秒")
    except OSError as exc:
        return CommandProbe(False, f"无法启动：{exc}")
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    if completed.returncode:
        return CommandProbe(
            False,
            f"健康检查退出码 {completed.returncode}：{output or '无输出'}",
        )
    return CommandProbe(True, output or "命令可正常启动")
