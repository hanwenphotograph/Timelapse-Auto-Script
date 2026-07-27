"""Inspect the managed resources used by SunsetScore 0.9.x."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


LLAMA_RELEASE = "b10040"
MODEL_NAME = "Qwen3VL-2B-Instruct-Q4_K_M.gguf"
MODEL_SIZE = 1_107_409_952
PROJECTOR_NAME = "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"
PROJECTOR_SIZE = 445_053_216


def sunset_data_home() -> Path:
    override = os.environ.get("SUNSETSCORE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SunsetScore"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return (
            Path(base) / "SunsetScore"
            if base
            else Path.home() / "AppData" / "Local" / "SunsetScore"
        )
    base = os.environ.get("XDG_DATA_HOME")
    return (
        Path(base).expanduser() / "SunsetScore"
        if base
        else Path.home() / ".local" / "share" / "SunsetScore"
    )


def inspect_sunset_resources() -> dict[str, tuple[str, str]]:
    home = sunset_data_home()
    return {
        "sunset_runtime": _runtime_status(home),
        "sunset_model": _artifact_status(home / "models" / MODEL_NAME, MODEL_SIZE),
        "sunset_projector": _artifact_status(
            home / "models" / PROJECTOR_NAME, PROJECTOR_SIZE
        ),
    }


def _artifact_status(path: Path, expected_size: int) -> tuple[str, str]:
    try:
        size = path.stat().st_size
    except OSError:
        return "missing", f"尚未下载 · {path}"
    if size != expected_size:
        return (
            "issue",
            f"文件不完整（{_format_size(size)} / {_format_size(expected_size)}）",
        )
    return "ready", f"已下载 {_format_size(size)} · {path}"


def _runtime_status(home: Path) -> tuple[str, str]:
    runtime_root = home / "runtime"
    valid: list[tuple[str, Path]] = []
    try:
        candidates = tuple(runtime_root.glob(f"{LLAMA_RELEASE}-*"))
    except OSError:
        candidates = ()
    for candidate in candidates:
        marker = candidate / ".installed.json"
        try:
            document = json.loads(marker.read_text(encoding="utf-8"))
            relative = Path(document["executable"])
            if relative.is_absolute() or ".." in relative.parts:
                continue
            executable = candidate / relative
            server_name = (
                "llama-server.exe"
                if executable.suffix.lower() == ".exe"
                else "llama-server"
            )
            if document.get("release") != LLAMA_RELEASE:
                continue
            if executable.is_file() and executable.with_name(server_name).is_file():
                valid.append((str(document.get("backend", "cpu")).upper(), candidate))
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            continue
    if valid:
        backends = ", ".join(sorted({backend for backend, _path in valid}))
        return "ready", f"{LLAMA_RELEASE} · {backends} · {valid[0][1]}"
    if candidates:
        return "issue", f"发现不完整的运行时 · {runtime_root}"
    return "missing", f"尚未准备 · {runtime_root}"


def _format_size(size: int) -> str:
    if size >= 1024**3:
        return f"{size / 1024**3:.2f} GB"
    return f"{size / 1024**2:.0f} MB"
