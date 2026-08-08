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


def parse_hdr_ready(line: str, work_dir: Path) -> HdrReadyEvent | None:
    if not line.startswith(EVENT_PREFIX):
        return None
    try:
        document = json.loads(line[len(EVENT_PREFIX) :])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Bracketlapse 事件不是有效 JSON：{exc.msg}") from exc
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
