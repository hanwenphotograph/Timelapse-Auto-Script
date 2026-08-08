"""Cross-platform process discovery and termination."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import psutil

from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.errors import ProcessError
from timelapse_manager.paths import application_root


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


def resolve_command(
    primary: str,
    fallback: str | None = None,
    *,
    root: Path | None = None,
) -> list[str]:
    dependencies = DependencyPaths.discover(root or application_root())
    errors: list[str] = []
    for candidate in (primary, fallback):
        if not candidate:
            continue
        argv = split_command(candidate)
        executable = argv[0]
        resolved: Path | None
        if Path(executable).expanduser().is_absolute() or any(
            sep in executable for sep in ("/", "\\")
        ):
            path = Path(executable).expanduser()
            resolved = path.resolve() if path.is_file() else None
            if resolved is not None and not _allowed_executable(resolved, dependencies):
                errors.append(f"{executable}（不在应用私有目录）")
                continue
        else:
            resolved = _managed_executable(executable, dependencies)
        if resolved:
            argv[0] = str(resolved)
            return argv
        errors.append(executable)
    raise ProcessError("找不到应用私有命令: " + " / ".join(errors))


def _managed_executable(name: str, dependencies: DependencyPaths) -> Path | None:
    names = (name, f"{name}.exe") if os.name == "nt" else (name,)
    for directory in dependencies.command_directories():
        for candidate_name in names:
            candidate = directory / candidate_name
            if candidate.is_file() and (
                os.name == "nt" or os.access(candidate, os.X_OK)
            ):
                resolved = candidate.resolve()
                if dependencies.contains(resolved):
                    return resolved
    return None


def _allowed_executable(path: Path, dependencies: DependencyPaths) -> bool:
    if dependencies.contains(path):
        return True
    try:
        path.relative_to(dependencies.app_root)
        return True
    except ValueError:
        pass
    try:
        return path == Path(sys.executable).resolve()
    except OSError:
        return False


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
