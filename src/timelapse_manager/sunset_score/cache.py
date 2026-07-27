"""Validate whether a SunsetScore result matches current HDR images."""

from __future__ import annotations

import re
import stat
from pathlib import Path

from timelapse_manager.sunset_score.models import StoredScore


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png"}
NUMBER_PATTERN = re.compile(r"(\d+)")


class CacheMismatchError(ValueError):
    """The score file does not describe the current image inventory."""


def validate_score_inventory(
    score: StoredScore,
    hdr_dir: Path,
    *,
    interval: int,
    application_version: str,
    require_retry_safe: bool,
) -> Path:
    if score.application_version != application_version:
        raise CacheMismatchError(
            f"应用版本 {score.application_version} 与当前版本 {application_version} 不一致"
        )
    if score.interval != interval:
        raise CacheMismatchError(
            f"采样间隔 {score.interval} 与当前配置 {interval} 不一致"
        )
    images = discover_images(hdr_dir)
    if score.image_count != len(images):
        raise CacheMismatchError(
            f"图片总数 {score.image_count} 与当前数量 {len(images)} 不一致"
        )
    expected_sampled = (len(images) + interval - 1) // interval
    if score.sampled_count != expected_sampled:
        raise CacheMismatchError(
            f"采样数 {score.sampled_count} 与当前预期 {expected_sampled} 不一致"
        )
    sampled = images[::interval]
    for sample in score.samples:
        expected = sampled[sample.sample_index - 1]
        if sample.photo != expected.name:
            raise CacheMismatchError(
                f"样本 {sample.sample_index} 路径 {sample.photo!r} 与当前清单不一致"
            )
    if require_retry_safe and score.failed_count and not score.has_sunset:
        raise CacheMismatchError("缓存包含失败样本且未检测到晚霞")
    return _safe_sample_path(hdr_dir, score.highest.photo)


def discover_images(directory: Path) -> list[Path]:
    try:
        images = [
            path
            for path in directory.iterdir()
            if path.is_file()
            and not _is_link_or_reparse(path)
            and path.suffix.casefold() in SUPPORTED_SUFFIXES
        ]
    except OSError as exc:
        raise CacheMismatchError(f"无法扫描 HDR 目录 {directory}：{exc}") from exc
    images.sort(key=lambda path: _natural_path_key(path.name))
    return images


def _safe_sample_path(directory: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != value:
        raise CacheMismatchError(f"评分照片路径不安全：{value!r}")
    root = directory.resolve()
    candidate = (root / relative).resolve()
    if (
        candidate.parent != root
        or not candidate.is_file()
        or _is_link_or_reparse(candidate)
    ):
        raise CacheMismatchError(f"评分照片不存在或越界：{value!r}")
    return candidate


def _natural_text_key(value: str) -> tuple[tuple[int, object], ...]:
    chunks: list[tuple[int, object]] = []
    for chunk in NUMBER_PATTERN.split(value.casefold()):
        chunks.append((1, int(chunk)) if chunk.isdigit() else (0, chunk))
    return tuple(chunks)


def _natural_path_key(value: str) -> tuple[object, ...]:
    return (_natural_text_key(value), ((2, value),))


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
