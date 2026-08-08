"""Shared scoring behavior for the SunsetScore CLI test double."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import time


@dataclass
class Session:
    directory: Path
    scores: dict[str, dict] = field(default_factory=dict)
    failed: set[str] = field(default_factory=set)


def one_shot(directory: Path, interval: int, version: str, *, force: bool) -> int:
    score_path = directory / ".sunsetscore-score.json"
    if score_path.exists() and not force:
        return 0
    session = Session(directory)
    scan(session, interval)
    try:
        result, _path = write_session_score(session, interval, version)
    except ValueError:
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


def inventory(directory: Path, interval: int) -> tuple[list[Path], list[Path]]:
    images = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    return images, images[::interval]


def scan(session: Session, interval: int) -> int:
    _images, sampled = inventory(session.directory, interval)
    values = [
        int(value) for value in os.environ.get("FAKE_SUNSET_SCORES", "4").split(",")
    ]
    failed_indexes = {
        int(value)
        for value in os.environ.get("FAKE_SUNSET_FAILED_INDEXES", "").split(",")
        if value
    }
    attempted = 0
    for index, image in enumerate(sampled, start=1):
        if image.name in session.scores or image.name in session.failed:
            continue
        attempted += 1
        time.sleep(float(os.environ.get("FAKE_SUNSET_DELAY", "0")))
        if index in failed_indexes:
            session.failed.add(image.name)
            continue
        score = values[min(index - 1, len(values) - 1)]
        session.scores[image.name] = {
            "score": score,
            "reason": f"模拟评分理由 {score}",
        }
        record(f"score:{image.name}")
    return attempted


def write_session_score(
    session: Session, interval: int, version: str
) -> tuple[dict, Path]:
    images, sampled = inventory(session.directory, interval)
    samples = _samples(session, sampled)
    if not samples:
        raise ValueError("所有采样照片均评分失败")
    has_sunset, ranges = _summary(samples, len(sampled))
    scores = [item["score"] for item in samples]
    result = {
        "directory": str(session.directory),
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
    path = session.directory / ".sunsetscore-score.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return result, path


def record(value: str) -> None:
    target = os.environ.get("FAKE_SUNSET_MODEL_EVENTS")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as stream:
        stream.write(value + "\n")


def _samples(session: Session, sampled: list[Path]) -> list[dict]:
    samples = []
    for index, image in enumerate(sampled, start=1):
        score = session.scores.get(image.name)
        if score is not None:
            samples.append(
                {"sample_index": index, "photo": image.name, **score}
            )
    return samples


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
