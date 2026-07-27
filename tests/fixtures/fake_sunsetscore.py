#!/usr/bin/env python3
"""Small SunsetScore stand-in that writes the public score cache shape."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path


def _summary(samples: list[dict], sampled_count: int) -> tuple[bool, list[dict]]:
    high = {item["sample_index"]: item for item in samples if item["score"] >= 3}
    selected: dict[int, dict] = {}
    if sampled_count < 3:
        selected = high
    else:
        for start in range(1, sampled_count - 1):
            matches = [
                high[index] for index in range(start, start + 3) if index in high
            ]
            if len(matches) >= 2:
                selected.update((item["sample_index"], item) for item in matches)
    ordered = [selected[index] for index in sorted(selected)]
    ranges = []
    if ordered:
        first = previous = ordered[0]
        for current in ordered[1:]:
            if current["sample_index"] == previous["sample_index"] + 1:
                previous = current
                continue
            ranges.append(
                {"start_photo": first["photo"], "end_photo": previous["photo"]}
            )
            first = previous = current
        ranges.append({"start_photo": first["photo"], "end_photo": previous["photo"]})
    return bool(selected), ranges


def main() -> int:
    version = os.environ.get("FAKE_SUNSET_VERSION", "0.9.0")
    args = sys.argv[1:]
    if "--version" in args:
        print(f"sunsetscore {version}")
        return int(os.environ.get("FAKE_SUNSET_VERSION_EXIT_CODE", "0"))
    exit_code = int(os.environ.get("FAKE_SUNSET_EXIT_CODE", "0"))
    if exit_code:
        return exit_code

    directory = Path(args[0]).resolve()
    interval = int(args[args.index("--interval") + 1])
    score_path = directory / ".sunsetscore-score.json"
    if score_path.exists() and "--force" not in args:
        return 0
    images = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    sampled = images[::interval]
    values = [
        int(value) for value in os.environ.get("FAKE_SUNSET_SCORES", "4").split(",")
    ]
    failed = {
        int(value)
        for value in os.environ.get("FAKE_SUNSET_FAILED_INDEXES", "").split(",")
        if value
    }
    samples = []
    for index, image in enumerate(sampled, start=1):
        if index in failed:
            continue
        score = values[min(index - 1, len(values) - 1)]
        samples.append(
            {
                "sample_index": index,
                "photo": image.name,
                "score": score,
                "reason": f"模拟评分理由 {score}",
            }
        )
    if not samples:
        return 1
    has_sunset, ranges = _summary(samples, len(sampled))
    scores = [item["score"] for item in samples]
    result = {
        "directory": str(directory),
        "image_count": len(images),
        "sampled_count": len(sampled),
        "successful_count": len(samples),
        "failed_count": len(sampled) - len(samples),
        "interval": interval,
        "inference_workers": 1,
        "average_score": round(sum(scores) / len(scores), 2),
        "max_score": max(scores),
        "has_sunset": has_sunset,
        "sunset_ranges": ranges,
        "error": None,
    }
    document = {
        "format_version": 3,
        "application_version": version,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model_version": "fake-model",
        "inference_backend": "fake",
        "inference_device": "fake-device",
        "recursive": False,
        "result": result,
        "sample_scores": samples,
    }
    score_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
