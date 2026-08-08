"""Download verified private package-manager bootstraps."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from timelapse_manager.dependency_manager.paths import DependencyPaths
from timelapse_manager.errors import ProcessError


Output = Callable[[str], None] | None
UV_VERSION = "0.12.3"
HOMEBREW_VERSION = "6.0.15"
HOMEBREW_SHA256 = "abfcabf3ee5caab7acacf5286a1d4d6d0a9d2ba05564de603a355d77f546efc8"


@dataclass(frozen=True)
class Artifact:
    filename: str
    sha256: str

    @property
    def url(self) -> str:
        return f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{self.filename}"


UV_ARTIFACTS = {
    ("darwin", "arm64"): Artifact(
        "uv-aarch64-apple-darwin.tar.gz",
        "546f7f8a6c70ff13a3a9d2bc958db3427298cebf3e0cb756f9177133b7068843",
    ),
    ("darwin", "x86_64"): Artifact(
        "uv-x86_64-apple-darwin.tar.gz",
        "4c9f52262a14da336e4a42ed24992d12d0c956acde87619e4611d321dffa602b",
    ),
    ("linux", "aarch64"): Artifact(
        "uv-aarch64-unknown-linux-gnu.tar.gz",
        "bb66cb52e7b1823aed1183630d8d8e5c958840d584a4c55ec10a4cfc168dcca2",
    ),
    ("linux", "x86_64"): Artifact(
        "uv-x86_64-unknown-linux-gnu.tar.gz",
        "600cf9a742aca00d292673b16b5acffaa7b8c269a364ad0c2e79498dcb1fe101",
    ),
    ("windows", "amd64"): Artifact(
        "uv-x86_64-pc-windows-msvc.zip",
        "b23350c79e8ad0192b8124af13a0f17e8d4e4549524785e1aef389ae5a06990e",
    ),
    ("windows", "arm64"): Artifact(
        "uv-aarch64-pc-windows-msvc.zip",
        "4343217d668727b8a8eb5cad92389a1d2eeead93c89940d1b955ba1bb15462eb",
    ),
}


def ensure_uv(paths: DependencyPaths, output: Output = None) -> Path:
    paths.ensure_layout()
    executable = paths.uv_executable
    if executable.is_file():
        return executable
    key = (platform.system().lower(), platform.machine().lower())
    artifact = UV_ARTIFACTS.get(key)
    if artifact is None:
        raise ProcessError(f"当前平台没有受支持的私有 uv 构建：{key[0]}/{key[1]}")
    archive = download_verified(
        paths, artifact.url, artifact.filename, artifact.sha256, output
    )
    _extract_uv(archive, executable)
    if os.name != "nt":
        executable.chmod(executable.stat().st_mode | 0o755)
    _emit(output, f"私有 uv 已准备：{executable}")
    return executable


def ensure_homebrew(paths: DependencyPaths, output: Output = None) -> Path:
    paths.ensure_layout()
    executable = paths.homebrew_executable
    if executable.is_file():
        return executable
    if platform.system().lower() not in {"darwin", "linux"}:
        raise ProcessError("当前平台不支持私有 Homebrew 依赖环境")
    filename = f"homebrew-{HOMEBREW_VERSION}.tar.gz"
    url = (
        f"https://github.com/Homebrew/brew/archive/refs/tags/{HOMEBREW_VERSION}.tar.gz"
    )
    archive = download_verified(paths, url, filename, HOMEBREW_SHA256, output)
    staging = Path(tempfile.mkdtemp(prefix="homebrew-", dir=paths.bootstrap_dir))
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(staging, filter="data")
        roots = [item for item in staging.iterdir() if item.is_dir()]
        if len(roots) != 1:
            raise ProcessError("Homebrew 引导包结构无效")
        if paths.homebrew_dir.exists():
            shutil.rmtree(paths.homebrew_dir)
        roots[0].replace(paths.homebrew_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if not executable.is_file():
        raise ProcessError("Homebrew 引导包未生成预期可执行文件")
    _emit(output, f"私有 Homebrew 已准备：{executable}")
    return executable


def download_verified(
    paths: DependencyPaths,
    url: str,
    filename: str,
    sha256: str,
    output: Output,
) -> Path:
    downloads = paths.cache_dir / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    destination = downloads / filename
    if destination.is_file() and _sha256(destination) == sha256:
        return destination
    partial = destination.with_name(destination.name + ".part")
    _emit(output, f"正在下载 {filename}")
    try:
        with (
            urllib.request.urlopen(url, timeout=60) as response,
            partial.open("wb") as stream,
        ):
            shutil.copyfileobj(response, stream)
    except (OSError, urllib.error.URLError) as exc:
        partial.unlink(missing_ok=True)
        raise ProcessError(f"下载 {filename} 失败：{exc}") from exc
    if _sha256(partial) != sha256:
        partial.unlink(missing_ok=True)
        raise ProcessError(f"下载文件校验失败：{filename}")
    partial.replace(destination)
    return destination


def _extract_uv(archive: Path, destination: Path) -> None:
    name = "uv.exe" if os.name == "nt" else "uv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            member = next(
                (
                    item
                    for item in bundle.infolist()
                    if Path(item.filename).name == name
                ),
                None,
            )
            if member is None:
                raise ProcessError("uv 引导包缺少可执行文件")
            with bundle.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
        return
    with tarfile.open(archive, "r:gz") as bundle:
        member = next(
            (item for item in bundle.getmembers() if Path(item.name).name == name),
            None,
        )
        source = bundle.extractfile(member) if member is not None else None
        if source is None:
            raise ProcessError("uv 引导包缺少可执行文件")
        with source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _emit(output: Output, message: str) -> None:
    if output:
        output(message)
