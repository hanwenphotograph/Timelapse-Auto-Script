"""Daily processing eligibility, using the host's local calendar and timezone."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from timelapse_manager.errors import ConfigError


DEFAULT_PROCESSING_TIME = {"mode": "immediate", "start_at": "00:00"}


def validate_processing_time(value: Any) -> None:
    if not isinstance(value, dict):
        raise ConfigError("photo_processing 必须是映射")
    if value.get("mode") not in ("immediate", "scheduled"):
        raise ConfigError("照片处理时间必须选择即时或自定义时间")
    start = value.get("start_at")
    if not isinstance(start, str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", start
    ):
        raise ConfigError("照片处理开始时间必须使用 HH:MM 格式，例如 00:00")


def is_deferred(project: dict[str, Any]) -> bool:
    return (
        project.get("photo_processing", DEFAULT_PROCESSING_TIME)["mode"] == "scheduled"
    )


def requires_processing_tools(task: dict[str, Any], project: dict[str, Any]) -> bool:
    return bool(task["processing"].get("enabled", True)) and (
        task["preset"] in {"processing", "eternal"} or not is_deferred(project)
    )


def processing_due_at(project: dict[str, Any], ready_at: str) -> datetime:
    """Return the first daily start after this material became ready.

    Construct each date in local time instead of adding 24 hours to a fixed UTC
    offset, so the daily wall-clock time also survives DST changes.
    """
    ready = datetime.fromisoformat(ready_at)
    local = ready.astimezone().replace(tzinfo=None)
    options = project.get("photo_processing", DEFAULT_PROCESSING_TIME)
    if options["mode"] == "immediate":
        return ready.astimezone()
    hour, minute = map(int, options["start_at"].split(":"))
    due = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if due < local:
        due += timedelta(days=1)
    return due.astimezone()


def processing_ready(
    project: dict[str, Any], ready_at: str, now: datetime | None = None
) -> bool:
    return (now or datetime.now().astimezone()) >= processing_due_at(project, ready_at)
