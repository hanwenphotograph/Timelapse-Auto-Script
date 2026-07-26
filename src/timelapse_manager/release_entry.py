"""Windowed frozen entry point used by Release packages."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from timelapse_manager.cli import main as cli_main


def release_arguments(arguments: Sequence[str]) -> list[str]:
    values = list(arguments)
    return values or ["gui"]


def main(arguments: Sequence[str] | None = None) -> int:
    os.environ.setdefault("TIMELAPSE_MANAGER_BUILD_MODE", "release")
    values = sys.argv[1:] if arguments is None else arguments
    return cli_main(release_arguments(values))


if __name__ == "__main__":
    raise SystemExit(main())
