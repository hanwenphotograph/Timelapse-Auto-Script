"""Dependency checks used by the source GUI launchers.

This module intentionally depends only on the Python standard library so it can
run before the project's pip dependencies have been installed.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path


PIP_MODULES = ("yaml", "psutil", "PIL", "customtkinter")


def pip_dependencies_ready() -> bool:
    """Return whether every pip-provided runtime module is installed.

    ``customtkinter`` is located without importing it because importing it also
    imports Tkinter.  Tkinter is a Python/system component and is checked
    separately below.
    """

    try:
        return all(importlib.util.find_spec(name) is not None for name in PIP_MODULES)
    except (ImportError, ValueError):
        return False


def tkinter_ready() -> bool:
    """Return whether this interpreter has a working, display-free Tcl runtime."""

    try:
        tkinter = importlib.import_module("tkinter")
        interpreter = tkinter.Tcl()
        interpreter.eval("info patchlevel")
    except Exception:
        return False
    return True


def runtime_dependencies_ready() -> bool:
    """Return whether the complete GUI import stack is usable."""

    if not tkinter_ready():
        return False
    try:
        for name in PIP_MODULES:
            importlib.import_module(name)
    except Exception:
        return False
    return True


def homebrew_tk_formula(
    base_executable: str | Path | None = None,
    version_info: Sequence[int] | None = None,
) -> str | None:
    """Return the matching Homebrew Tk formula for a Homebrew interpreter."""

    executable = Path(
        base_executable or getattr(sys, "_base_executable", None) or sys.executable
    )
    try:
        executable = executable.expanduser().resolve()
    except OSError:
        executable = executable.expanduser().absolute()
    normalized = executable.as_posix()
    if "/Cellar/python" not in normalized and "/opt/python" not in normalized:
        return None

    version = version_info or sys.version_info
    if len(version) < 2 or int(version[0]) != 3:
        return None
    return f"python-tk@{int(version[0])}.{int(version[1])}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "check",
        choices=("packages", "tkinter", "runtime", "homebrew-formula"),
    )
    args = parser.parse_args(argv)

    if args.check == "packages":
        return 0 if pip_dependencies_ready() else 1
    if args.check == "tkinter":
        return 0 if tkinter_ready() else 1
    if args.check == "runtime":
        return 0 if runtime_dependencies_ready() else 1

    formula = homebrew_tk_formula()
    if not formula:
        return 1
    print(formula)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
