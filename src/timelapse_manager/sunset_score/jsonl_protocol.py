"""Small helpers for SunsetScore's public JSONL wire format."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from timelapse_manager.errors import ProcessError


PROTOCOL_VERSION = 1


class SunsetScoreProtocolError(ProcessError):
    """SunsetScore's public service is unavailable or returned invalid JSONL."""


@dataclass(frozen=True)
class PendingRequest:
    command: str
    session_id: str | None


def encode_request(
    request_id: int,
    command: str,
    *,
    session_id: str | None,
    directory: str | None,
) -> str:
    request: dict[str, Any] = {"id": request_id, "command": command}
    if session_id is not None:
        request["session"] = session_id
    if directory is not None:
        request["directory"] = directory
    return json.dumps(request, ensure_ascii=False, separators=(",", ":"))


def decode_event(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def ready_error(value: dict[str, Any], application_version: str) -> str:
    if value.get("protocol_version") != PROTOCOL_VERSION:
        return "SunsetScore JSONL 协议版本不受支持"
    if value.get("application_version") != application_version:
        return "SunsetScore 就绪事件的应用版本与探测结果不一致"
    return ""


def format_scan_response(
    session_id: str | None, value: dict[str, Any]
) -> str | None:
    if value.get("event") == "error":
        return (
            f"晚霞增量扫描失败：{session_id or '-'}；"
            f"{value.get('error') or '未知错误'}"
        )
    if value.get("event") != "scan_complete":
        return None
    return (
        f"晚霞增量扫描完成：{session_id or '-'}；"
        f"照片 {value.get('image_count', 0)} 张，"
        f"采样 {value.get('sampled_count', 0)} 张"
    )
