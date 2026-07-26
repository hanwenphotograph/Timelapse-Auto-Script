#!/usr/bin/env python3
"""Build a platform-native Release portable ZIP without a console."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_package import build  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    archive = build("release")
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
