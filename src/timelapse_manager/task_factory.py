"""Materialize preset selections into persisted task definitions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from timelapse_manager.config import LoadedConfig
from timelapse_manager.errors import ConfigError
from timelapse_manager.io_utils import deep_merge, now_iso
from timelapse_manager.presets import PRESET_DESCRIPTIONS, SCHEMA_VERSION
from timelapse_manager.schedule import TimeSlot, select_next_slot


def _common(task_id: str, name: str, preset: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": task_id,
        "name": name.strip() or task_id,
        "preset": preset,
        "created_at": now_iso(),
        "capture": {},
        "processing": {"enabled": True},
        "cleanup": {
            "enabled": False,
            "keep_directories": ["hdr_enfuse", "hdr_video"],
            "delete_incomplete_groups": False,
            "on_failure": False,
        },
        "retry": {"enabled": False},
        "environment": {},
    }


def _manual_template(task_id: str, name: str) -> dict[str, Any]:
    task = _common(task_id, name, "manual")
    task["capture"] = {
        "work_dir": None,
        "start_date": None,
        "start_at": None,
        "end_date": None,
        "end_at": None,
        "interval_seconds": None,
    }
    return task


def _eternal_template(task_id: str, name: str) -> dict[str, Any]:
    task = _common(task_id, name, "eternal")
    task["capture"] = {"interval_seconds": None}
    task["cleanup"].update(
        {"enabled": True, "delete_incomplete_groups": True, "on_failure": True}
    )
    task["retry"] = {"enabled": True, "delay_seconds": None}
    task["eternal"] = {
        "batch_groups": None,
        "images_per_group": None,
        "state_dir": None,
    }
    return task


def _slot_name(chain_name: str, slot: TimeSlot) -> str:
    return f"{chain_name} · {slot.label} {slot.work_date.isoformat()}"


def materialize_scheduled(
    config: LoadedConfig,
    task_id: str,
    name: str,
    source_preset: str,
    *,
    now: datetime | None = None,
    continuation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if source_preset not in {"scheduled_once", "scheduled_loop"}:
        raise ConfigError(f"无法展开定时预设: {source_preset}")
    project = config.project
    slot = select_next_slot(project["morning"], project["dusk"], now)
    chain_name = str((continuation or {}).get("chain_name") or name).strip() or task_id
    display_name = _slot_name(chain_name, slot) if source_preset == "scheduled_loop" else name
    task = _common(task_id, display_name, "manual")
    work_dir = config.auto_root / slot.work_date.isoformat() / slot.directory_name
    task["capture"] = {
        "work_dir": str(work_dir),
        "start_date": slot.work_date.isoformat(),
        "start_at": slot.start_at,
        "end_date": slot.work_date.isoformat(),
        "end_at": slot.end_at,
        "interval_seconds": project["capture_interval_seconds"],
    }
    task["cleanup"].update(
        {"enabled": True, "delete_incomplete_groups": True, "on_failure": True}
    )
    if source_preset == "scheduled_loop":
        current = continuation or {}
        task["retry"] = {
            "enabled": True,
            "delay_seconds": project["runtime"]["retry_delay_seconds"],
        }
        task["continuation"] = {
            "enabled": True,
            "chain_id": str(current.get("chain_id") or task_id),
            "chain_name": chain_name,
            "sequence": int(current.get("sequence", 1)),
            "source_preset": "scheduled_loop",
        }
        previous = current.get("previous_task_id")
        if previous:
            task["continuation"]["previous_task_id"] = str(previous)
    return task


def create_task_definition(
    config: LoadedConfig,
    task_id: str,
    name: str,
    preset: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if preset not in PRESET_DESCRIPTIONS:
        raise ConfigError(f"未知预设: {preset}")
    if preset in {"scheduled_once", "scheduled_loop"}:
        return materialize_scheduled(config, task_id, name, preset, now=now)
    if preset == "eternal":
        return _eternal_template(task_id, name)
    return _manual_template(task_id, name)


def migrate_legacy_scheduled(
    config: LoadedConfig, raw: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    preset = str(raw.get("preset", ""))
    generated = materialize_scheduled(
        config,
        str(raw.get("id", "")),
        str(raw.get("name", "")),
        preset,
        now=now,
    )
    generated["created_at"] = raw.get("created_at") or generated["created_at"]
    for key in ("processing", "cleanup", "environment"):
        if isinstance(raw.get(key), dict):
            generated[key] = deep_merge(generated[key], raw[key])
    capture = raw.get("capture")
    if isinstance(capture, dict) and capture.get("interval_seconds") is not None:
        generated["capture"]["interval_seconds"] = capture["interval_seconds"]
    retry = raw.get("retry")
    if isinstance(retry, dict):
        if preset == "scheduled_loop" and retry.get("delay_seconds") is not None:
            generated["retry"]["delay_seconds"] = retry["delay_seconds"]
        if retry.get("enabled") is False:
            generated["retry"]["enabled"] = False
    return generated


def create_successor_definition(
    config: LoadedConfig,
    task_id: str,
    predecessor: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    continuation = deepcopy(predecessor["continuation"])
    continuation.update(
        {
            "sequence": int(continuation["sequence"]) + 1,
            "previous_task_id": predecessor["id"],
        }
    )
    return materialize_scheduled(
        config,
        task_id,
        continuation["chain_name"],
        continuation["source_preset"],
        now=now,
        continuation=continuation,
    )
