"""Shared PyInstaller portable-package builder."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal


BuildMode = Literal["debug", "release"]
ROOT = Path(__file__).resolve().parents[1]
APPLICATION_NAME = "TimelapseManager"


def platform_name(system: str | None = None) -> str:
    value = (system or platform.system()).lower()
    if value == "windows":
        return "win"
    if value == "darwin":
        return "mac"
    if value == "linux":
        return "linux"
    return value.replace(" ", "-")


def pyinstaller_command(
    mode: BuildMode, build_root: Path, *, python: str | None = None
) -> list[str]:
    if mode not in {"debug", "release"}:
        raise ValueError(f"未知构建模式: {mode}")
    entrypoint = (
        ROOT / "timelapse.py"
        if mode == "debug"
        else ROOT / "src" / "timelapse_manager" / "release_entry.py"
    )
    return [
        python or sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console" if mode == "debug" else "--windowed",
        "--name",
        APPLICATION_NAME,
        "--collect-all",
        "customtkinter",
        "--paths",
        str(ROOT / "src"),
        "--distpath",
        str(build_root / "dist"),
        "--workpath",
        str(build_root / "work"),
        "--specpath",
        str(build_root / "spec"),
        str(entrypoint),
    ]


def _generated_application(
    dist_root: Path, mode: BuildMode, tag: str
) -> Path:
    candidates = [dist_root / APPLICATION_NAME]
    if mode == "release" and tag == "mac":
        candidates.insert(0, dist_root / f"{APPLICATION_NAME}.app")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    expected = " 或 ".join(str(path) for path in candidates)
    raise RuntimeError(f"PyInstaller 未生成预期目录: {expected}")


def _copy_payload(package_dir: Path) -> None:
    config_dir = package_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "config" / "auto_timelapse.example.yaml", config_dir)
    shutil.copy2(ROOT / "config" / "webhook.example.yaml", config_dir)
    for filename in ("README.md", "README_CN.md", "requirements.txt"):
        shutil.copy2(ROOT / filename, package_dir)


def _stage_application(
    source: Path, package_dir: Path, mode: BuildMode, tag: str
) -> None:
    if package_dir.parent.exists():
        shutil.rmtree(package_dir.parent)
    package_dir.mkdir(parents=True)
    if source.suffix == ".app":
        shutil.copytree(source, package_dir / source.name)
    else:
        shutil.copytree(source, package_dir, dirs_exist_ok=True)
    _copy_payload(package_dir)
    if mode != "debug":
        return
    launcher_name = {"win": "start_gui.bat", "mac": "start_gui.command"}.get(tag)
    if not launcher_name:
        return
    launcher = package_dir / launcher_name
    shutil.copy2(ROOT / launcher_name, launcher)
    if tag == "mac":
        launcher.chmod(launcher.stat().st_mode | 0o111)


def build(mode: BuildMode) -> Path:
    tag = platform_name()
    build_root = ROOT / "build" / mode / tag
    subprocess.run(
        pyinstaller_command(mode, build_root),
        cwd=ROOT,
        check=True,
    )
    source = _generated_application(build_root / "dist", mode, tag)
    package_parent = build_root / "package"
    package_dir = package_parent / APPLICATION_NAME
    _stage_application(source, package_dir, mode, tag)

    label = "Debug" if mode == "debug" else "Release"
    timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
    archive_dir = ROOT / "bin" / f"{label}-Archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_base = archive_dir / (
        f"{APPLICATION_NAME}-{tag}-{mode}-portable-{timestamp}"
    )
    return Path(
        shutil.make_archive(
            str(archive_base),
            "zip",
            root_dir=package_parent,
            base_dir=APPLICATION_NAME,
        )
    )
