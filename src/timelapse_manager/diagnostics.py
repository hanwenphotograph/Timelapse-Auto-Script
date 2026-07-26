"""Command-line self-test checks."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from timelapse_manager.io_utils import load_yaml, save_yaml
from timelapse_manager.process_utils import resolve_command
from timelapse_manager.service import ManagerService


@dataclass(frozen=True)
class CheckResult:
    level: str
    name: str
    detail: str


def run_self_test(service: ManagerService, *, full: bool = False) -> list[CheckResult]:
    results: list[CheckResult] = []

    def check(name: str, operation) -> None:
        try:
            detail = operation()
            results.append(CheckResult("PASS", name, str(detail or "通过")))
        except Exception as exc:
            results.append(CheckResult("FAIL", name, str(exc)))

    check("Python 版本", lambda: _check_python())
    check("项目配置", lambda: f"已加载 {service.paths.config_file}")
    check("运行目录写入", lambda: _check_writable(service.store.runtime_dir))
    check("YAML 双向读写", _check_yaml_roundtrip)
    check("子进程启动", _check_subprocess)
    check("GUI 模块", _check_gui_import)
    check("任务配置", lambda: _check_tasks(service))

    commands = service.config.project["commands"]
    command_checks = (
        ("camera-timelapse", commands["camera"], None),
        (
            "Bracketlapse",
            commands["bracketlapse"],
            commands.get("bracketlapse_fallback"),
        ),
    )
    for name, primary, fallback in command_checks:
        try:
            resolved = resolve_command(primary, fallback)
            results.append(CheckResult("PASS", f"外部命令 {name}", resolved[0]))
        except Exception as exc:
            results.append(
                CheckResult("FAIL" if full else "WARN", f"外部命令 {name}", str(exc))
            )
    return results


def _check_python() -> str:
    if sys.version_info < (3, 10):
        raise RuntimeError("需要 Python 3.10 或更高版本")
    return sys.version.split()[0]


def _check_writable(directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="self-test-", dir=str(directory))
    os.close(descriptor)
    Path(name).unlink()
    return str(directory)


def _check_yaml_roundtrip() -> str:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "roundtrip.yaml"
        expected = {"中文": "可读写", "nested": {"value": 3}}
        save_yaml(path, expected)
        if load_yaml(path) != expected:
            raise RuntimeError("YAML 往返结果不一致")
    return "UTF-8 YAML 正常"


def _check_subprocess() -> str:
    if getattr(sys, "frozen", False):
        result = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        if result.returncode != 0 or "timelapse-manager" not in result.stdout:
            raise RuntimeError(f"打包入口子进程退出码 {result.returncode}")
        return "打包入口子进程正常"
    result = subprocess.run(
        [sys.executable, "-c", "print('timelapse-self-test')"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "timelapse-self-test":
        raise RuntimeError(f"子进程退出码 {result.returncode}")
    return "创建和读取输出正常"


def _check_gui_import() -> str:
    import customtkinter
    import tkinter

    interpreter = tkinter.Tcl()
    interpreter.eval("info patchlevel")
    from timelapse_manager import gui  # noqa: F401

    return f"CustomTkinter {customtkinter.__version__} / Tk {tkinter.TkVersion}"


def _check_tasks(service: ManagerService) -> str:
    tasks = service.store.list_definitions()
    errors = [task.get("_error") for task in tasks if task.get("_error")]
    if errors:
        raise RuntimeError("; ".join(str(error) for error in errors))
    return f"{len(tasks)} 个任务定义可读取"
