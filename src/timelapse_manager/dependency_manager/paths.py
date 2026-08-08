"""Private dependency paths and isolated subprocess environments."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


RESERVED_ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "VIRTUAL_ENV_PROMPT",
        "CONDA_PREFIX",
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
        "LD_LIBRARY_PATH",
        "HOME",
        "USERPROFILE",
        "XDG_CACHE_HOME",
        "PIP_CACHE_DIR",
        "PIPX_HOME",
        "PIPX_BIN_DIR",
        "PYTHONNOUSERSITE",
        "HOMEBREW_PREFIX",
        "HOMEBREW_CELLAR",
        "HOMEBREW_REPOSITORY",
        "HOMEBREW_CACHE",
        "UV_CACHE_DIR",
        "UV_PYTHON_INSTALL_DIR",
        "UV_MANAGED_PYTHON",
        "UV_PYTHON_DOWNLOADS",
        "SUNSETSCORE_HOME",
        "TIMELAPSE_DEPENDENCIES_ROOT",
    }
)


@dataclass(frozen=True)
class DependencyPaths:
    app_root: Path

    @classmethod
    def discover(cls, app_root: Path) -> "DependencyPaths":
        return cls(app_root.expanduser().resolve())

    @property
    def root(self) -> Path:
        return self.app_root / ".timelapse" / "dependencies"

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    @property
    def bootstrap_dir(self) -> Path:
        return self.root / "bootstrap"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def home_dir(self) -> Path:
        return self.root / "home"

    @property
    def python_dir(self) -> Path:
        return self.root / "python"

    @property
    def python_executable(self) -> Path:
        if os.name == "nt":
            return self.python_dir / "Scripts" / "python.exe"
        return self.python_dir / "bin" / "python"

    @property
    def python_bin_dir(self) -> Path:
        return self.python_executable.parent

    @property
    def uv_executable(self) -> Path:
        return self.bootstrap_dir / ("uv.exe" if os.name == "nt" else "uv")

    @property
    def homebrew_dir(self) -> Path:
        return self.root / "homebrew"

    @property
    def homebrew_executable(self) -> Path:
        return self.homebrew_dir / "bin" / "brew"

    @property
    def applications_dir(self) -> Path:
        return self.root / "applications"

    @property
    def sunsetscore_home(self) -> Path:
        return self.root / "sunsetscore"

    @property
    def source_dir(self) -> Path:
        return self.root / "sources"

    def ensure_layout(self) -> None:
        for directory in (
            self.root,
            self.bin_dir,
            self.bootstrap_dir,
            self.cache_dir,
            self.home_dir,
            self.applications_dir,
            self.source_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def command_directories(self) -> tuple[Path, ...]:
        directories = (
            self.bin_dir,
            self.python_bin_dir,
            self.homebrew_dir / "bin",
            self.homebrew_dir / "sbin",
        )
        return tuple(dict.fromkeys(path.resolve() for path in directories))

    def contains(self, path: Path) -> bool:
        try:
            path.expanduser().resolve().relative_to(self.root.resolve())
        except (OSError, ValueError):
            return False
        return True

    def runtime_environment(
        self, base: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        environment = dict(os.environ if base is None else base)
        for name in RESERVED_ENVIRONMENT_KEYS:
            environment.pop(name, None)
        environment.update(self._private_values())
        environment["PATH"] = os.pathsep.join(
            str(path) for path in (*self.command_directories(), *_system_directories())
        )
        return environment

    def install_environment(
        self, base: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        environment = self.runtime_environment(base)
        environment.update(
            {
                "HOMEBREW_CACHE": str(self.cache_dir / "homebrew"),
                "HOMEBREW_NO_ANALYTICS": "1",
                "HOMEBREW_NO_AUTO_UPDATE": "1",
                "HOMEBREW_NO_ENV_HINTS": "1",
                "HOMEBREW_NO_INSTALL_CLEANUP": "1",
                "HOMEBREW_FORCE_BOTTLE": "1",
                "UV_CACHE_DIR": str(self.cache_dir / "uv"),
                "UV_PYTHON_INSTALL_DIR": str(self.root / "python-builds"),
                "UV_MANAGED_PYTHON": "1",
                "UV_PYTHON_DOWNLOADS": "automatic",
            }
        )
        return environment

    def _private_values(self) -> dict[str, str]:
        return {
            "HOME": str(self.home_dir),
            "USERPROFILE": str(self.home_dir),
            "XDG_CACHE_HOME": str(self.cache_dir),
            "PIP_CACHE_DIR": str(self.cache_dir / "pip"),
            "SUNSETSCORE_HOME": str(self.sunsetscore_home),
            "TIMELAPSE_DEPENDENCIES_ROOT": str(self.root),
            "VIRTUAL_ENV": str(self.python_dir),
            "PYTHONNOUSERSITE": "1",
            "HOMEBREW_PREFIX": str(self.homebrew_dir),
            "HOMEBREW_CELLAR": str(self.homebrew_dir / "Cellar"),
            "HOMEBREW_REPOSITORY": str(self.homebrew_dir),
        }


def _system_directories() -> tuple[Path, ...]:
    if os.name == "nt":
        windows = os.environ.get("SystemRoot", r"C:\Windows")
        return Path(windows) / "System32", Path(windows)
    return tuple(Path(value) for value in ("/usr/bin", "/bin", "/usr/sbin", "/sbin"))
