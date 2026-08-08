"""Prepare the pinned Simple Deflicker source inside the private prefix."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

from timelapse_manager.dependency_manager.bootstrap import download_verified
from timelapse_manager.dependency_manager.install_runner import run_install_command
from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.errors import ProcessError


COMMIT = "6981a617671fedf29c67f47551a1bd6f4b99ee1a"
SHA256 = "cfb69176411bb472f5c220f10e71d6f3a28f710f7e94efa30ef96ab49afb9485"
URL = f"https://github.com/SHthemW/simple-deflicker/archive/{COMMIT}.tar.gz"


def prepare_source(
    paths: DependencyPaths,
    output: Callable[[str], None] | None = None,
) -> Path:
    destination = paths.source_dir / "simple-deflicker"
    marker = destination / ".timelapse-commit"
    if marker.is_file() and marker.read_text(encoding="ascii").strip() == COMMIT:
        return destination
    archive = download_verified(
        paths,
        URL,
        f"simple-deflicker-{COMMIT}.tar.gz",
        SHA256,
        output,
    )
    staging = Path(tempfile.mkdtemp(prefix="simple-deflicker-", dir=paths.source_dir))
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(staging, filter="data")
        roots = [item for item in staging.iterdir() if item.is_dir()]
        if len(roots) != 1:
            raise ProcessError("Simple Deflicker 源码包结构无效")
        if destination.exists():
            shutil.rmtree(destination)
        roots[0].replace(destination)
        marker.write_text(COMMIT + "\n", encoding="ascii")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return destination


def build_environment(paths: DependencyPaths) -> dict[str, str]:
    environment = paths.install_environment()
    environment.update(
        {
            "GOCACHE": str(paths.cache_dir / "go" / "build"),
            "GOMODCACHE": str(paths.cache_dir / "go" / "modules"),
            "GOPATH": str(paths.cache_dir / "go" / "workspace"),
        }
    )
    return environment


def install(
    paths: DependencyPaths,
    output: Callable[[str], None] | None = None,
) -> None:
    source = prepare_source(paths, output)
    executable = paths.bin_dir / (
        "simple-deflicker.exe" if os.name == "nt" else "simple-deflicker"
    )
    command = (
        str(paths.homebrew_dir / "bin" / "go"),
        "build",
        "-tags",
        "cli",
        "-o",
        str(executable),
    )
    run_install_command(
        command,
        cwd=source,
        environment=build_environment(paths),
        on_output=output,
    )
