"""Finalize native tools that are distributed as application bundles."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from timelapse_manager.dependency_manager.health import (
    probe_command,
    tool_probe_arguments,
)
from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.errors import ProcessError


def link_hugin_tools(paths: DependencyPaths) -> None:
    _clear_macos_quarantine(paths.applications_dir)
    environment = paths.runtime_environment()
    for name in ("enfuse", "align_image_stack"):
        matches = list(paths.applications_dir.rglob(name))
        source = next((path for path in matches if "tools_mac" in path.parts), None)
        if source is None:
            raise ProcessError(f"Hugin 安装包缺少 {name}")
        destination = paths.bin_dir / name
        destination.unlink(missing_ok=True)
        destination.symlink_to(source)
        probe = probe_command(
            (str(source),),
            tool_probe_arguments(name),
            env=environment,
        )
        if not probe.ready:
            raise ProcessError(f"Hugin 工具 {name} 不可用：{probe.detail}")


def _clear_macos_quarantine(root: Path) -> None:
    if sys.platform != "darwin":
        return
    try:
        completed = subprocess.run(
            ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProcessError(f"无法清除 Hugin 下载隔离属性：{exc}") from exc
    if completed.returncode:
        detail = completed.stderr.strip() or f"退出码 {completed.returncode}"
        raise ProcessError(f"无法清除 Hugin 下载隔离属性：{detail}")
