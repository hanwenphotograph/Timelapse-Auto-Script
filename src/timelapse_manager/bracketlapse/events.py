"""Parse machine-readable Bracketlapse process events."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


EVENT_PREFIX = "BRACKETLAPSE_EVENT "


@dataclass(frozen=True)
class HdrReadyEvent:
    frame_number: int
    path: Path


@dataclass(frozen=True)
class VideoProgressEvent:
    event: str
    path: Path
    completed: int
    total: int


def parse_hdr_ready(line: str, work_dir: Path) -> HdrReadyEvent | None:
    document = _parse_document(line)
    if not isinstance(document, dict) or document.get("event") != "hdr_ready":
        return None
    frame_number = document.get("frame_number")
    value = document.get("path")
    if type(frame_number) is not int or frame_number < 1:
        raise ValueError("Bracketlapse hdr_ready 的 frame_number 无效")
    if not isinstance(value, str) or not value:
        raise ValueError("Bracketlapse hdr_ready 的 path 无效")
    expected = (work_dir / "hdr_enfuse").resolve()
    path = Path(value).expanduser().resolve()
    if path.parent != expected or not path.is_file() or path.is_symlink():
        raise ValueError(f"Bracketlapse hdr_ready 路径不安全：{value}")
    return HdrReadyEvent(frame_number, path)


def parse_video_progress(
    line: str,
    work_dir: Path,
) -> VideoProgressEvent | None:
    document = _parse_document(line)
    if not isinstance(document, dict):
        return None
    event = document.get("event")
    if not isinstance(event, str) or event not in {
        "video_started",
        "video_progress",
        "video_completed",
    }:
        return None
    value = document.get("path")
    completed = document.get("completed")
    total = document.get("total")
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise ValueError("Bracketlapse 视频事件的 path 无效")
    if (
        type(completed) is not int
        or type(total) is not int
        or total <= 0
        or completed < 0
        or completed > total
    ):
        raise ValueError("Bracketlapse 视频事件的 completed/total 无效")
    if event == "video_started" and completed != 0:
        raise ValueError("Bracketlapse video_started 必须从 0 开始")
    if event == "video_completed" and completed != total:
        raise ValueError("Bracketlapse video_completed 必须完成全部帧")
    path = Path(value).resolve()
    if path == work_dir.resolve() or not path.is_relative_to(work_dir.resolve()):
        raise ValueError(f"Bracketlapse 视频事件路径不安全：{value}")
    return VideoProgressEvent(str(event), path, completed, total)


def _parse_document(line: str) -> object:
    if not line.startswith(EVENT_PREFIX):
        return None
    try:
        return json.loads(line[len(EVENT_PREFIX) :])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Bracketlapse 事件不是有效 JSON：{exc.msg}") from exc
