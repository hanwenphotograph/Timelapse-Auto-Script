"""macOS-specific bundle metadata, signing, and archive helpers."""

from __future__ import annotations

import plistlib
import runpy
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_IDENTIFIER = "io.github.hanwenphotograph.timelapse-manager"
APPLICATION_VERSION = str(
    runpy.run_path(str(ROOT / "src" / "timelapse_manager" / "__init__.py"))[
        "__version__"
    ]
)


def finalize_application(application: Path) -> None:
    plist_path = application / "Contents" / "Info.plist"
    with plist_path.open("rb") as stream:
        info = plistlib.load(stream)
    info.update(
        {
            "CFBundleIdentifier": BUNDLE_IDENTIFIER,
            "CFBundleShortVersionString": APPLICATION_VERSION,
            "CFBundleVersion": APPLICATION_VERSION,
        }
    )
    with plist_path.open("wb") as stream:
        plistlib.dump(info, stream)
    subprocess.run(
        ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(application)],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/codesign",
            "--verify",
            "--all-architectures",
            "--deep",
            "--strict",
            str(application),
        ],
        check=True,
    )


def create_archive(package_dir: Path, archive_base: Path) -> Path:
    archive = archive_base.with_suffix(".zip")
    archive.unlink(missing_ok=True)
    subprocess.run(
        [
            "/usr/bin/zip",
            "-q",
            "-r",
            "-y",
            str(archive),
            package_dir.name,
        ],
        cwd=package_dir.parent,
        check=True,
    )
    return archive
