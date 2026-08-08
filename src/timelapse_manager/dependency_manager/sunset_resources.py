"""Consume SunsetScore's public managed-resource status command."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from timelapse_manager.sunset_score.availability import (
    SunsetScoreAvailability,
    detect_sunset_score,
)


RESOURCE_IDS = {
    "runtime": "sunset_runtime",
    "model": "sunset_model",
    "projector": "sunset_projector",
}
VALID_STATES = {"ready", "missing", "issue"}


@dataclass(frozen=True)
class SunsetResourceSnapshot:
    command: tuple[str, ...]
    statuses: dict[str, tuple[str, str]]
    artifacts: tuple[tuple[str, int], ...] = ()


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def inspect_sunset_resources(
    value: str | SunsetScoreAvailability,
    *,
    run: RunCommand = subprocess.run,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, tuple[str, str]]:
    return query_sunset_resources(value, run=run, root=root, env=env).statuses


def query_sunset_resources(
    value: str | SunsetScoreAvailability,
    *,
    run: RunCommand = subprocess.run,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> SunsetResourceSnapshot:
    availability = (
        value
        if isinstance(value, SunsetScoreAvailability)
        else detect_sunset_score(value, root=root, env=env)
    )
    if not availability.enabled:
        state = "issue" if availability.command else "missing"
        return _failed_snapshot(state, availability.reason)
    try:
        completed = run(
            [*availability.command, "runtime", "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
            env=dict(env) if env is not None else None,
        )
    except subprocess.TimeoutExpired:
        return _failed_snapshot(
            "issue", "SunsetScore 资源状态检查超时", availability.command
        )
    except OSError as exc:
        return _failed_snapshot(
            "issue", f"SunsetScore 资源状态检查失败：{exc}", availability.command
        )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        return _failed_snapshot(
            "issue",
            f"SunsetScore 资源状态命令失败：{detail or completed.returncode}",
            availability.command,
        )
    try:
        document = json.loads(completed.stdout)
        statuses, artifacts = _parse_document(document, availability.version)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return _failed_snapshot(
            "issue", f"SunsetScore 资源状态无效：{exc}", availability.command
        )
    return SunsetResourceSnapshot(availability.command, statuses, artifacts)


def _parse_document(
    document: object,
    application_version: str | None,
) -> tuple[dict[str, tuple[str, str]], tuple[tuple[str, int], ...]]:
    if not isinstance(document, dict) or not isinstance(document.get("resources"), dict):
        raise ValueError("缺少 resources 对象")
    if document.get("application_version") != application_version:
        raise ValueError("application_version 与版本探测结果不一致")
    resources = document["resources"]
    statuses = {}
    artifacts = []
    for public_id, manager_id in RESOURCE_IDS.items():
        item = resources.get(public_id)
        if not isinstance(item, dict):
            raise ValueError(f"缺少资源 {public_id}")
        state = item.get("state")
        detail = item.get("detail")
        if state not in VALID_STATES or not isinstance(detail, str) or not detail:
            raise ValueError(f"资源 {public_id} 的状态无效")
        statuses[manager_id] = (state, detail)
        artifact = item.get("artifact")
        if artifact is not None:
            artifacts.append(_parse_artifact(artifact, public_id))
    return statuses, tuple(artifacts)


def _parse_artifact(value: object, resource_id: str) -> tuple[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"资源 {resource_id} 的 artifact 无效")
    filename = value.get("filename")
    size = value.get("size")
    if not isinstance(filename, str) or not filename or type(size) is not int or size < 1:
        raise ValueError(f"资源 {resource_id} 的 artifact 无效")
    return filename, size


def _failed_snapshot(
    state: str, detail: str, command: tuple[str, ...] = ()
) -> SunsetResourceSnapshot:
    statuses = {
        manager_id: (state, detail or "SunsetScore 不可用")
        for manager_id in RESOURCE_IDS.values()
    }
    return SunsetResourceSnapshot(command, statuses)
