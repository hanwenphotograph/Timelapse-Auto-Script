#!/usr/bin/env python3
"""Small camera-timelapse stand-in used by integration tests."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--start-at")
    parser.add_argument("--start-day")
    parser.add_argument("--end-at")
    parser.add_argument("--end-day")
    parser.add_argument("--interval")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rounds = int(os.environ.get("FAKE_CAMERA_ROUNDS", "2"))
    delay = float(os.environ.get("FAKE_CAMERA_DELAY", "0.04"))
    for group in range(1, rounds + 1):
        print(f"Starting capture round {group}", flush=True)
        for exposure in range(3):
            (args.output_dir / f"{group:04d}_{exposure}.jpg").write_bytes(b"fake-jpeg")
        print(f"Deleting group {group} from camera", flush=True)
        time.sleep(delay)
    if args.end_at:
        print(
            f"Scheduled end time {args.end_at} reached; stopping after this round",
            flush=True,
        )
    return int(os.environ.get("FAKE_CAMERA_EXIT_CODE", "0"))


if __name__ == "__main__":
    raise SystemExit(main())
