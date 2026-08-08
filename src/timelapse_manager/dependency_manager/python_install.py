"""Create the managed Python environment used by owned CLI packages."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from timelapse_manager.dependency_manager.bootstrap import ensure_uv
from timelapse_manager.dependency_manager.install_runner import run_install_plan
from timelapse_manager.dependency_manager.models import InstallPlan
from timelapse_manager.dependency_manager.paths import DependencyPaths


def ensure_private_python(
    paths: DependencyPaths,
    root: Path,
    on_output: Callable[[str], None] | None = None,
) -> None:
    uv = ensure_uv(paths, on_output)
    if paths.python_executable.is_file():
        return
    plan = InstallPlan(
        (
            str(uv),
            "venv",
            "--python",
            "3.12",
            "--managed-python",
            "--seed",
            str(paths.python_dir),
        ),
        "",
    )
    run_install_plan(
        plan,
        cwd=root,
        environment=paths.install_environment(),
        on_output=on_output,
    )
