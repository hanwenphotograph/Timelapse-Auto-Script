"""Select supported system package-manager commands."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


def system_install_command(package: str) -> tuple[str, ...] | None:
    system = platform.system().lower()
    if system == "darwin":
        brew = _find_program("brew")
        formula = {"gphoto2": "gphoto2", "ffmpeg": "ffmpeg"}.get(package)
        return (brew, "install", formula) if brew and formula else None
    if system == "linux":
        return _apt_command(package)
    if system == "windows" and package == "ffmpeg":
        winget = shutil.which("winget")
        if winget:
            return (
                winget,
                "install",
                "--id",
                "Gyan.FFmpeg",
                "--exact",
                "--accept-package-agreements",
                "--accept-source-agreements",
            )
    return None


def _apt_command(package: str) -> tuple[str, ...] | None:
    apt = shutil.which("apt-get")
    packages = {
        "gphoto2": ("gphoto2",),
        "ffmpeg": ("ffmpeg",),
        "hugin": ("enblend", "hugin-tools"),
    }.get(package)
    if not apt or not packages:
        return None
    prefix: tuple[str, ...] = ()
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        pkexec = shutil.which("pkexec")
        if not pkexec:
            return None
        prefix = (pkexec,)
    return (*prefix, apt, "install", "-y", *packages)


def _find_program(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for directory in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        candidate = directory / name
        if candidate.is_file():
            return str(candidate)
    return None
