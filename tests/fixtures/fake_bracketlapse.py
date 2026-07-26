#!/usr/bin/env python3
"""Small Bracketlapse stand-in used by integration tests."""

from __future__ import annotations

import sys
import time
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--standby":
        work_dir = Path(args[1])
        time.sleep(0.25)
    else:
        work_dir = Path(args[0])
    work_dir.mkdir(parents=True, exist_ok=True)
    print("Fusing fake exposure groups", flush=True)
    hdr = work_dir / "hdr_enfuse"
    hdr.mkdir(exist_ok=True)
    (hdr / "frame-0001.jpg").write_bytes(b"not-a-real-image")
    print("Deflickering fused frames.", flush=True)
    video = work_dir / "hdr_video"
    video.mkdir(exist_ok=True)
    (video / "timelapse.mp4").write_bytes(b"fake-video")
    print("Creating video from fake frames", flush=True)
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
