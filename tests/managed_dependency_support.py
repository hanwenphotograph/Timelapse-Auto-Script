from __future__ import annotations

import os
from pathlib import Path

from timelapse_manager.dependency_manager.paths import DependencyPaths


def install_fake_native_tools(root: Path) -> DependencyPaths:
    paths = DependencyPaths.discover(root)
    paths.ensure_layout()
    for name in ("gphoto2", "enfuse", "ffmpeg", "simple-deflicker"):
        filename = f"{name}.cmd" if os.name == "nt" else name
        executable = paths.bin_dir / filename
        if os.name == "nt":
            executable.write_text("@echo off\nexit /b 0\n", encoding="ascii")
        else:
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
            executable.chmod(0o755)
    return paths
