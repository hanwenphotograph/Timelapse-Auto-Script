"""Build a lightweight macOS app around the selected source environment."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


APP_NAME = "TimelapseManager.app"
BUNDLE_IDENTIFIER = "io.github.hanwenphotograph.timelapse-manager.source"
EXECUTABLE_NAME = "TimelapseManager"
ICON_NAME = "timelapse-manager.icns"
PREPARE_ERROR = 78


@dataclass(frozen=True)
class PythonEnvironment:
    runtime: Path
    executable: Path
    prefix: Path


def current_environment() -> PythonEnvironment:
    base_prefix = Path(sys.base_prefix).resolve()
    framework_runtime = (
        base_prefix / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    )
    runtime = framework_runtime if framework_runtime.is_file() else Path(sys.executable)
    return PythonEnvironment(
        runtime=runtime.resolve(),
        executable=Path(sys.executable).expanduser().absolute(),
        prefix=Path(sys.prefix).resolve(),
    )


def build_source_application(
    root: Path,
    environment: PythonEnvironment | None = None,
    *,
    sign: bool = True,
) -> Path:
    environment = environment or current_environment()
    icon = Path(__file__).with_name("assets") / ICON_NAME
    _validate_inputs(environment, icon)
    output_root = root.resolve() / ".timelapse" / "source-launcher"
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="build-", dir=output_root))
    try:
        application = staging / APP_NAME
        executable = _assemble_application(application, environment, icon)
        if sign:
            _sign_application(application, executable)
            smoke_environment = os.environ.copy()
            smoke_environment["__PYVENV_LAUNCHER__"] = str(
                environment.executable
            )
            subprocess.run(
                [str(executable), "-c", "import customtkinter, tkinter, yaml"],
                check=True,
                env=smoke_environment,
                stdout=subprocess.DEVNULL,
            )
        destination = output_root / APP_NAME
        if destination.exists():
            shutil.rmtree(destination)
        application.replace(destination)
        return destination
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _validate_inputs(environment: PythonEnvironment, icon: Path) -> None:
    required = (
        environment.runtime,
        environment.executable,
        environment.prefix,
        icon,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "macOS source application input is missing: " + ", ".join(missing)
        )


def _assemble_application(
    application: Path,
    environment: PythonEnvironment,
    icon: Path,
) -> Path:
    contents = application / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    for directory in (macos, resources):
        directory.mkdir(parents=True)
    executable = macos / EXECUTABLE_NAME
    shutil.copy2(environment.runtime, executable)
    executable.chmod(
        executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    shutil.copy2(icon, resources / ICON_NAME)
    with (contents / "Info.plist").open("wb") as stream:
        plistlib.dump(_bundle_info(), stream)
    return executable


def _bundle_info() -> dict[str, object]:
    return {
        "CFBundleDisplayName": "TimelapseManager",
        "CFBundleExecutable": EXECUTABLE_NAME,
        "CFBundleIconFile": ICON_NAME,
        "CFBundleIdentifier": BUNDLE_IDENTIFIER,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "TimelapseManager",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "NSHighResolutionCapable": True,
    }


def _sign_application(application: Path, executable: Path) -> None:
    subprocess.run(
        ["/usr/bin/codesign", "--remove-signature", str(executable)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "/usr/bin/codesign",
            "--force",
            "--deep",
            "--sign",
            "-",
            str(application),
        ],
        check=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        parser.error("this launcher is only available on macOS")
    root = args.root.resolve()
    environment = current_environment()
    try:
        application = build_source_application(root, environment)
        executable = application / "Contents" / "MacOS" / EXECUTABLE_NAME
        process_environment = os.environ.copy()
        process_environment["__PYVENV_LAUNCHER__"] = str(
            environment.executable
        )
        process_environment["VIRTUAL_ENV"] = str(environment.prefix)
        process_environment["PATH"] = os.pathsep.join(
            (
                str(environment.executable.parent),
                process_environment.get("PATH", ""),
            )
        )
        command = [
            str(executable),
            str(root / "timelapse.py"),
            *(args.arguments or ["gui"]),
        ]
        os.execve(executable, command, process_environment)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Unable to prepare the macOS source application: {exc}", file=sys.stderr)
        return PREPARE_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
