#!/usr/bin/env python3
"""Small Bracketlapse stand-in used by integration tests."""

from __future__ import annotations

import base64
import json
import os
import re
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
    if "--version" in args:
        print("bracketlapse 0.2.0")
        return 0
    if args and args[0] == "--standby":
        work_dir = Path(args[1])
        quiet_seconds = min(float(args[3]), 0.1)
        return _run_standby(work_dir, quiet_seconds)
    work_dir = Path(args[0])
    work_dir.mkdir(parents=True, exist_ok=True)
    groups = _complete_groups(work_dir)
    frame_count = int(
        os.environ.get("FAKE_BRACKET_FRAMES", str(len(groups) or 1))
    )
    _fuse_missing(work_dir, frame_count)
    _finalize(work_dir, args)
    return 0


def _run_standby(work_dir: Path, quiet_seconds: float) -> int:
    work_dir.mkdir(parents=True, exist_ok=True)
    observed_groups = 0
    last_change = time.monotonic()
    armed = False
    while True:
        groups = _complete_groups(work_dir)
        if len(groups) != observed_groups:
            observed_groups = len(groups)
            last_change = time.monotonic()
            armed = True
            _fuse_missing(work_dir, observed_groups)
        if armed and time.monotonic() - last_change >= quiet_seconds:
            break
        time.sleep(0.01)
    frame_count = int(
        os.environ.get("FAKE_BRACKET_FRAMES", str(observed_groups or 1))
    )
    _fuse_missing(work_dir, frame_count)
    _finalize(work_dir, [])
    return 0


def _complete_groups(work_dir: Path) -> list[int]:
    counts: dict[int, int] = {}
    for path in work_dir.iterdir():
        if not path.is_file():
            continue
        match = re.match(r"^(\d+)_", path.name)
        if match is not None:
            group = int(match.group(1))
            counts[group] = counts.get(group, 0) + 1
    return sorted(group for group, count in counts.items() if count >= 3)


def _fuse_missing(work_dir: Path, frame_count: int) -> None:
    hdr = work_dir / "hdr_enfuse"
    hdr.mkdir(exist_ok=True)
    for index in range(1, frame_count + 1):
        output = hdr / f"frame-{index:04d}.jpg"
        if output.exists():
            continue
        print(f"Fusing fake exposure group {index}", flush=True)
        time.sleep(float(os.environ.get("FAKE_BRACKET_DELAY", "0")))
        output.write_bytes(JPEG_BYTES)
        print(
            "BRACKETLAPSE_EVENT "
            + json.dumps(
                {
                    "event": "hdr_ready",
                    "frame_number": index,
                    "path": str(output.resolve()),
                },
                separators=(",", ":"),
            ),
            flush=True,
        )


def _finalize(work_dir: Path, args: list[str]) -> None:
    if "--no-deflick" not in args:
        print("Deflickering fused frames.", flush=True)
    if "--no-video" not in args:
        video = work_dir / "hdr_video"
        video.mkdir(exist_ok=True)
        (video / "timelapse.mp4").write_bytes(b"fake-video")
        print("Creating video from fake frames", flush=True)
    print("Done.", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
