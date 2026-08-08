"""Stream one dependency installation command to the GUI."""

from __future__ import annotations

import subprocess
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path

from timelapse_manager.dependency_manager.models import InstallPlan
from timelapse_manager.dependency_manager.progress import InstallProgressTracker


class InstallCommandError(RuntimeError):
    pass


def run_install_plan(
    plan: InstallPlan,
    *,
    cwd: Path,
    environment: dict[str, str],
    on_output: Callable[[str], None] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    run_install_command(
        plan.command,
        cwd=cwd,
        environment=environment,
        progress_sizes=plan.progress_sizes,
        on_output=on_output,
        on_progress=on_progress,
    )


def run_install_command(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    progress_sizes: tuple[tuple[str, int], ...] = (),
    on_output: Callable[[str], None] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    try:
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env={**environment, "PYTHONUNBUFFERED": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise InstallCommandError(f"无法启动安装命令：{exc}") from exc
    tail: deque[str] = deque(maxlen=12)
    progress = InstallProgressTracker(progress_sizes)
    assert process.stdout is not None
    with process.stdout:
        for line in process.stdout:
            message = line.strip()
            if not message:
                continue
            tail.append(message)
            if on_output:
                on_output(message)
            value = progress.consume(message)
            if value is not None and on_progress:
                on_progress(value)
    code = process.wait()
    if code:
        detail = "\n".join(tail) or f"退出码 {code}"
        raise InstallCommandError(f"安装命令执行失败：\n{detail}")
