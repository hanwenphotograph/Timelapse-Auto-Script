#!/usr/bin/env python3
"""Small SunsetScore stand-in that implements its public CLI contracts."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from fake_sunsetscore_core import one_shot
from fake_sunsetscore_server import serve_jsonl


def main() -> int:
    version = os.environ.get("FAKE_SUNSET_VERSION", "0.10.0")
    args = sys.argv[1:]
    if "--version" in args:
        print(f"sunsetscore {version}")
        return int(os.environ.get("FAKE_SUNSET_VERSION_EXIT_CODE", "0"))
    exit_code = int(os.environ.get("FAKE_SUNSET_EXIT_CODE", "0"))
    if exit_code:
        return exit_code
    if "--serve-jsonl" in args:
        interval = int(args[args.index("--interval") + 1])
        return serve_jsonl(version, interval)

    directory = Path(args[0]).resolve()
    interval = int(args[args.index("--interval") + 1])
    return one_shot(
        directory,
        interval,
        version,
        force="--force" in args,
    )


if __name__ == "__main__":
    raise SystemExit(main())
