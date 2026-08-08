"""Build and execute private dependency installation plans."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from timelapse_manager.dependency_manager.bootstrap import ensure_homebrew
from timelapse_manager.dependency_manager.install_runner import (
    InstallCommandError,
    run_install_plan,
)
from timelapse_manager.dependency_manager.native_tools import link_hugin_tools
from timelapse_manager.dependency_manager.models import InstallPlan
from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.dependency_manager.python_install import ensure_private_python
from timelapse_manager.dependency_manager.simple_deflicker import (
    install as install_simple_deflicker,
)
from timelapse_manager.dependency_manager.sources import (
    PACKAGE_URLS as SOURCE_PACKAGE_URLS,
    SOURCE_REPOSITORIES,
    package_install_url,
)
from timelapse_manager.dependency_manager.sunset_resources import query_sunset_resources
from timelapse_manager.dependency_manager.system_install import (
    expand_formula_install_command,
    system_install_command,
)
from timelapse_manager.errors import ProcessError
from timelapse_manager.process_utils import format_command


PACKAGE_URLS = SOURCE_PACKAGE_URLS


class DependencyInstallError(RuntimeError):
    pass


class DependencyInstaller:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.paths = DependencyPaths.discover(self.root)

    def plan(
        self,
        action_id: str,
        commands: dict[str, Any],
        *,
        branch: str | None = None,
    ) -> InstallPlan | None:
        kind, _, value = action_id.partition(":")
        if kind == "python":
            return self._python_package_plan(value, branch)
        if kind == "system":
            return self._system_package_plan(value)
        if kind == "tool":
            return self._tool_plan(value)
        if action_id == "sunset:prepare":
            return self._sunset_plan(commands)
        return None

    def execute(
        self,
        plan: InstallPlan,
        on_output: Callable[[str], None] | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        self.paths.ensure_layout()
        if plan.bootstrap == "python":
            try:
                ensure_private_python(self.paths, self.root, on_output)
            except InstallCommandError as exc:
                raise DependencyInstallError(str(exc)) from exc
        elif plan.bootstrap == "homebrew":
            ensure_homebrew(self.paths, on_output)
        environment = self.paths.install_environment()
        environment.update(dict(plan.environment))
        try:
            expanded = expand_formula_install_command(plan.command, environment)
        except ProcessError as exc:
            raise DependencyInstallError(str(exc)) from exc
        if expanded != plan.command:
            plan = replace(plan, command=expanded)
        self._run(plan, environment, on_output, on_progress)
        if plan.post_install == "hugin":
            link_hugin_tools(self.paths)
        elif plan.post_install == "simple-deflicker":
            try:
                install_simple_deflicker(self.paths, on_output)
            except InstallCommandError as exc:
                raise DependencyInstallError(str(exc)) from exc
        if on_progress:
            on_progress(1.0)

    def _python_package_plan(
        self, package: str, branch: str | None
    ) -> InstallPlan | None:
        source = SOURCE_REPOSITORIES.get(package)
        if source is None:
            return None
        selected_branch = branch or source.default_branch
        url = package_install_url(package, branch)
        if not url:
            return None
        command = (
            str(self.paths.uv_executable),
            "pip",
            "install",
            "--python",
            str(self.paths.python_executable),
            "--upgrade",
            url,
        )
        variable = {
            "camera": "CAMERA_TIMELAPSE_BUILD_BRANCH",
            "bracketlapse": "BRACKETLAPSE_BUILD_BRANCH",
            "sunsetscore": "SUNSETSCORE_BUILD_BRANCH",
        }[package]
        return InstallPlan(
            command,
            self._confirmation(command, f"源码分支：{selected_branch}"),
            bootstrap="python",
            environment=((variable, selected_branch),),
        )

    def _system_package_plan(self, package: str) -> InstallPlan | None:
        command = system_install_command(package, self.paths)
        if not command:
            return None
        return InstallPlan(
            command,
            self._confirmation(command, "原生工具将安装到应用私有目录"),
            bootstrap="homebrew",
            post_install="hugin" if package == "hugin" else None,
        )

    def _tool_plan(self, package: str) -> InstallPlan | None:
        if package != "simple-deflicker":
            return None
        command = (
            str(self.paths.homebrew_executable),
            "install",
            "--force-bottle",
            "go",
        )
        return InstallPlan(
            command,
            self._confirmation(command, "将构建固定版本的 Simple Deflicker"),
            bootstrap="homebrew",
            post_install="simple-deflicker",
        )

    def _sunset_plan(self, commands: dict[str, Any]) -> InstallPlan | None:
        snapshot = query_sunset_resources(
            str(commands.get("sunsetscore", "sunsetscore")),
            root=self.root,
            env=self.paths.runtime_environment(),
        )
        if not snapshot.command:
            return None
        command = (*snapshot.command, "runtime", "prepare")
        return InstallPlan(
            command,
            self._confirmation(command, "将下载约 1.6 GB 的模型与推理运行时"),
            snapshot.artifacts,
        )

    def _run(
        self,
        plan: InstallPlan,
        environment: dict[str, str],
        on_output: Callable[[str], None] | None,
        on_progress: Callable[[float], None] | None,
    ) -> None:
        try:
            run_install_plan(
                plan,
                cwd=self.root,
                environment=environment,
                on_output=on_output,
                on_progress=on_progress,
            )
        except InstallCommandError as exc:
            raise DependencyInstallError(str(exc)) from exc

    def _confirmation(self, command: tuple[str, ...], detail: str) -> str:
        return (
            f"{detail}\n\n安装目录：{self.paths.root}\n\n"
            f"将执行：\n{format_command(command)}\n\n是否继续？"
        )
