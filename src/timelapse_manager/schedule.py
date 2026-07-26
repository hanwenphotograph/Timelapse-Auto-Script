"""Schedule selection compatible with the original shell preset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from timelapse_manager.errors import ConfigError


@dataclass(frozen=True)
class TimeSlot:
    label: str
    work_date: date
    start_at: str
    end_at: str

    @property
    def directory_name(self) -> str:
        return f"{self.start_at.replace(':', '')}-{self.end_at.replace(':', '')}"


def time_minutes(value: str, label: str = "时间") -> int:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label}必须使用 HH:MM 格式，当前值: {value!r}") from exc
    return parsed.hour * 60 + parsed.minute


def validate_schedule(morning: dict[str, str], dusk: dict[str, str]) -> None:
    morning_start = time_minutes(morning.get("start_at", ""), "清晨开始时间")
    morning_end = time_minutes(morning.get("end_at", ""), "清晨结束时间")
    dusk_start = time_minutes(dusk.get("start_at", ""), "黄昏开始时间")
    dusk_end = time_minutes(dusk.get("end_at", ""), "黄昏结束时间")
    if morning_start >= morning_end:
        raise ConfigError("清晨时间段必须在同一天内按升序设置")
    if dusk_start >= dusk_end:
        raise ConfigError("黄昏时间段必须在同一天内按升序设置")
    if morning_end >= dusk_start:
        raise ConfigError("黄昏开始时间必须晚于清晨结束时间")


def select_next_slot(
    morning: dict[str, str], dusk: dict[str, str], now: datetime | None = None
) -> TimeSlot:
    validate_schedule(morning, dusk)
    current = now or datetime.now().astimezone()
    current_minutes = current.hour * 60 + current.minute
    morning_end = time_minutes(morning["end_at"])
    dusk_end = time_minutes(dusk["end_at"])

    if current_minutes < morning_end:
        return TimeSlot("清晨", current.date(), morning["start_at"], morning["end_at"])
    if current_minutes < dusk_end:
        return TimeSlot("黄昏", current.date(), dusk["start_at"], dusk["end_at"])
    return TimeSlot(
        "清晨",
        current.date() + timedelta(days=1),
        morning["start_at"],
        morning["end_at"],
    )
