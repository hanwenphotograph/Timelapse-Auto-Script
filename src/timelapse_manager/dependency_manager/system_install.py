"""Create commands that install native tools into the private prefix."""

from __future__ import annotations

import platform
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence

from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.errors import ProcessError


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
FORMULA_NAME = re.compile(r"[A-Za-z0-9@+_.-]+(?:/[A-Za-z0-9@+_.-]+)*")


def system_install_command(
    package: str,
    paths: DependencyPaths,
    *,
    system: str | None = None,
) -> tuple[str, ...] | None:
    current = (system or platform.system()).lower()
    if current not in {"darwin", "linux"}:
        return None
    brew = str(paths.homebrew_executable)
    formula = {"gphoto2": "gphoto2", "ffmpeg": "ffmpeg"}.get(package)
    if formula:
        return brew, "install", "--force-bottle", formula
    if package == "hugin" and current == "darwin":
        return (
            brew,
            "install",
            "--cask",
            f"--appdir={paths.applications_dir}",
            "hugin",
        )
    return None


def expand_formula_install_command(
    command: Sequence[str],
    environment: Mapping[str, str],
    *,
    run: RunCommand = subprocess.run,
) -> tuple[str, ...]:
    values = tuple(command)
    if len(values) != 4 or values[1:3] != ("install", "--force-bottle"):
        return values
    formula = values[3]
    try:
        completed = run(
            [
                values[0],
                "deps",
                "--formula",
                "--include-build",
                "--topological",
                formula,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            env=dict(environment),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProcessError(f"无法解析 {formula} 的私有 bottle 依赖：{exc}") from exc
    if completed.returncode:
        detail = completed.stderr.strip() or f"退出码 {completed.returncode}"
        raise ProcessError(f"无法解析 {formula} 的私有 bottle 依赖：{detail}")
    dependencies = []
    for line in completed.stdout.splitlines():
        name = line.strip()
        if not name:
            continue
        if not FORMULA_NAME.fullmatch(name):
            raise ProcessError(f"Homebrew 返回了无效的 formula 名称：{name}")
        dependencies.append(name)
    targets = tuple(dict.fromkeys((*dependencies, formula)))
    return values[:3] + targets
