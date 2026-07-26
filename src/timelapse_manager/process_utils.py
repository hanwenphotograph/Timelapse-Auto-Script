"""Cross-platform process discovery and termination."""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Sequence

import psutil

from timelapse_manager.errors import ProcessError


def process_identity(pid: int) -> float | None:
    try:
        return psutil.Process(pid).create_time()
    except (psutil.Error, ValueError):
        return None


def process_matches(pid: int | None, created_at: float | None = None) -> bool:
    if not pid:
        return False
    try:
        process = psutil.Process(int(pid))
        if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
            return False
        return (
            created_at is None or abs(process.create_time() - float(created_at)) < 0.01
        )
    except (psutil.Error, ValueError, TypeError):
        return False


def split_command(value: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        raise ProcessError("外部命令不能为空")
    parts = shlex.split(value, posix=os.name != "nt")
    if os.name == "nt":
        parts = [
            part[1:-1]
            if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"}
            else part
            for part in parts
        ]
    return parts


def resolve_command(primary: str, fallback: str | None = None) -> list[str]:
    errors: list[str] = []
    for candidate in (primary, fallback):
        if not candidate:
            continue
        argv = split_command(candidate)
        executable = argv[0]
        resolved: str | None
        if Path(executable).expanduser().is_absolute() or any(
            sep in executable for sep in ("/", "\\")
        ):
            path = Path(executable).expanduser()
            resolved = str(path.resolve()) if path.is_file() else None
        else:
            resolved = shutil.which(executable)
        if resolved:
            argv[0] = resolved
            return argv
        errors.append(executable)
    raise ProcessError("找不到外部命令: " + " / ".join(errors))


def child_creation_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return 0


def detached_creation_flags() -> int:
    if os.name == "nt":
        return (
            subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        )
    return 0


def terminate_tree(pid: int, timeout: float = 10.0) -> None:
    if pid <= 0 or pid == os.getpid():
        raise ProcessError(f"拒绝终止无效或当前进程 PID: {pid}")
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    processes = parent.children(recursive=True)
    processes.append(parent)
    for process in reversed(processes):
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied as exc:
            raise ProcessError(f"没有权限终止 PID {process.pid}") from exc
    _, alive = psutil.wait_procs(processes, timeout=max(timeout, 0.1))
    for process in alive:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if alive:
        psutil.wait_procs(alive, timeout=2)


def signal_interrupt(pid: int) -> None:
    if os.name == "nt":
        try:
            os.kill(pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            return
        except (OSError, ValueError):
            terminate_tree(pid)
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGINT)
        except (OSError, ProcessLookupError):
            terminate_tree(pid)


def format_command(argv: Sequence[str]) -> str:
    return subprocess.list2cmdline(list(argv)) if os.name == "nt" else shlex.join(argv)
