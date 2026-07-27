#!/usr/bin/env python3
"""Small Bracketlapse stand-in used by integration tests."""

from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path


JPEG_BYTES = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkS"
    "Ew8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJ"
    "CQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjL/wAARCAAQABgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEA"
    "AAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIh"
    "MUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6"
    "Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZ"
    "mqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx"
    "8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA"
    "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAV"
    "YnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hp"
    "anN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPE"
    "xcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCO"
    "iiivmj7wKKKKAP/Z"
)


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
    frame_count = int(os.environ.get("FAKE_BRACKET_FRAMES", "1"))
    for index in range(1, frame_count + 1):
        (hdr / f"frame-{index:04d}.jpg").write_bytes(JPEG_BYTES)
    print("Deflickering fused frames.", flush=True)
    video = work_dir / "hdr_video"
    video.mkdir(exist_ok=True)
    (video / "timelapse.mp4").write_bytes(b"fake-video")
    print("Creating video from fake frames", flush=True)
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
