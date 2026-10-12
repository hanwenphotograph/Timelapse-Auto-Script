"""Detect attached cameras through the managed gPhoto2 public CLI."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.errors import ProcessError
from timelapse_manager.io_utils import now_iso
from timelapse_manager.process_utils import resolve_command


@dataclass(frozen=True)
class CameraDevice:
    model: str
    port: str


@dataclass(frozen=True)
class CameraConnection:
    status: str
    message: str
    devices: tuple[CameraDevice, ...] = ()
    checked_at: str = ""


def parse_devices(output: str) -> tuple[CameraDevice, ...]:
    devices: list[CameraDevice] = []
    for line in output.splitlines():
        match = re.fullmatch(r"\s*(.+?)\s+([a-z][a-z0-9+.-]*:\S+)\s*", line)
        if match:
            device = CameraDevice(match[1].strip(), match[2])
            if device not in devices:
                devices.append(device)
    return tuple(devices)


def detect_connection(root: Path, *, timeout: float = 10) -> CameraConnection:
    def result(status: str, message: str, devices=()) -> CameraConnection:
        return CameraConnection(status, message, devices, now_iso())

    try:
        command = resolve_command("gphoto2", root=root)
    except ProcessError:
        return result("unavailable", "缺少相机检测依赖，请在包管理中安装 gPhoto2")
    environment = DependencyPaths.discover(root).runtime_environment()
    environment["LC_ALL"] = "C"
    try:
        completed = subprocess.run(
            [*command, "--auto-detect"],
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return result("error", f"相机检测超过 {timeout:g} 秒，请稍后刷新")
    except OSError as exc:
        return result("error", f"无法检测相机：{exc}")
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[:300]
        return result("error", f"相机检测失败：{detail or '检测命令异常退出'}")
    devices = parse_devices(completed.stdout)
    if devices:
        return result(
            "connected", "\n".join(f"{d.model}\n{d.port}" for d in devices), devices
        )
    return result("disconnected", "未检测到相机，请确认电源和 USB 连接")
