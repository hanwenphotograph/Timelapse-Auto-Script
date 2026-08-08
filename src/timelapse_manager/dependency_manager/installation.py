"""Build and execute cross-platform dependency installation plans."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from timelapse_manager.dependency_manager.progress import InstallProgressTracker
from timelapse_manager.dependency_manager.sunset_resources import (
    query_sunset_resources,
)
from timelapse_manager.process_utils import format_command
from timelapse_manager.dependency_manager.system_install import (
    system_install_command,
)


PACKAGE_URLS = {
    "camera": "git+https://github.com/hanwenphotograph/Camera-Timelapse-Controller.git",
    "bracketlapse": "git+https://github.com/hanwenphotograph/Bracketlapse.git",
    "sunsetscore": "git+https://github.com/hanwenphotograph/Sunset-Score.git",
}


class DependencyInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstallPlan:
    command: tuple[str, ...]
    confirmation: str
    progress_sizes: tuple[tuple[str, int], ...] = ()


class DependencyInstaller:
    def __init__(self, root: Path) -> None:
        self.root = root

    def plan(self, action_id: str, commands: dict[str, Any]) -> InstallPlan | None:
        kind, _, value = action_id.partition(":")
        if kind == "python":
            return self._python_package_plan(value)
        if kind == "system":
            return self._system_package_plan(value)
        if action_id == "sunset:prepare":
            return self._sunset_plan(commands)
        return None

    def execute(
        self,
        plan: InstallPlan,
        on_output: Callable[[str], None] | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        try:
            process = subprocess.Popen(
                list(plan.command),
                cwd=str(self.root),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise DependencyInstallError(f"无法启动安装命令：{exc}") from exc
        tail: deque[str] = deque(maxlen=12)
        progress = InstallProgressTracker(plan.progress_sizes)
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
            raise DependencyInstallError(f"安装命令执行失败：\n{detail}")
        if on_progress:
            on_progress(1.0)

    def _python_package_plan(self, package: str) -> InstallPlan | None:
        url = PACKAGE_URLS.get(package)
        if not url:
            return None
        if not getattr(sys, "frozen", False):
            command = (sys.executable, "-m", "pip", "install", "--upgrade", url)
        else:
            pipx = shutil.which("pipx")
            if not pipx:
                return None
            command = (pipx, "install", "--force", url)
        return InstallPlan(
            command,
            f"将执行以下命令并访问网络：\n\n{format_command(command)}\n\n是否继续？",
        )

    def _system_package_plan(self, package: str) -> InstallPlan | None:
        command = system_install_command(package)
        if not command:
            return None
        return InstallPlan(
            tuple(command),
            f"将使用系统包管理器安装依赖：\n\n{format_command(command)}\n\n是否继续？",
        )

    @staticmethod
    def _sunset_plan(commands: dict[str, Any]) -> InstallPlan | None:
        snapshot = query_sunset_resources(
            str(commands.get("sunsetscore", "sunsetscore"))
        )
        if not snapshot.command:
            return None
        return InstallPlan(
            (*snapshot.command, "runtime", "prepare"),
            "SunsetScore 将自动选择推理后端，并下载约 1.6 GB 的模型与运行时资源。"
            "根据平台和 GPU 情况，缓存占用可能更大。是否继续？",
            snapshot.artifacts,
        )
