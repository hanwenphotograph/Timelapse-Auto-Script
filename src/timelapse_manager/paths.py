"""Application path discovery for source and frozen builds."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def application_root() -> Path:
    override = os.environ.get("TIMELAPSE_MANAGER_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            bundle = next(
                (parent for parent in executable.parents if parent.suffix == ".app"),
                None,
            )
            if bundle is not None:
                return bundle.parent
        return executable.parent
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "timelapse.py").is_file():
        return source_root
    return Path.cwd().resolve()


@dataclass(frozen=True)
class AppPaths:
    root: Path
    config_file: Path
    webhook_file: Path

    @classmethod
    def discover(cls, root: Path | None = None) -> "AppPaths":
        base = (root or application_root()).expanduser().resolve()
        config_file = (
            Path(
                os.environ.get(
                    "AUTO_TIMELAPSE_CONFIG", base / "config" / "auto_timelapse.yaml"
                )
            )
            .expanduser()
            .resolve()
        )
        webhook_file = (
            Path(
                os.environ.get(
                    "AUTO_TIMELAPSE_WEBHOOK_CONFIG", base / "config" / "webhook.yaml"
                )
            )
            .expanduser()
            .resolve()
        )
        return cls(base, config_file, webhook_file)

    def resolve_from_root(self, value: str | os.PathLike[str]) -> Path:
        path = Path(os.path.expandvars(str(value))).expanduser()
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()
