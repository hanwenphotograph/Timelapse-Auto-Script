"""Strict reader for SunsetScore's persisted directory result."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from timelapse_manager.sunset_score.aggregation import summarize
from timelapse_manager.sunset_score.models import SampleScore, StoredScore, SunsetRange


SCORE_FILENAME = ".sunsetscore-score.json"
SCORE_FORMAT_VERSION = 3


class ScoreFileError(ValueError):
    """A SunsetScore result file is missing or structurally invalid."""


def read_score_file(path: Path) -> StoredScore:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScoreFileError(f"评分文件不存在：{path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScoreFileError(f"无法读取评分文件 {path}：{exc}") from exc
    try:
        return _parse_document(document)
    except (TypeError, ValueError) as exc:
        raise ScoreFileError(f"评分文件无效 {path}：{exc}") from exc


def _parse_document(document: Any) -> StoredScore:
    root = _mapping(document, "评分文件")
    if (
        _integer(root.get("format_version"), "format_version", 1)
        != SCORE_FORMAT_VERSION
    ):
        raise ValueError("不支持的 format_version")
    application_version = _text(root.get("application_version"), "application_version")
    for key in (
        "generated_at",
        "model_version",
        "inference_backend",
        "inference_device",
    ):
        _text(root.get(key), key)
    if root.get("recursive") is not False:
        raise ValueError("recursive 必须为 false")

    result = _mapping(root.get("result"), "result")
    _text(result.get("directory"), "result.directory")
    _integer(result.get("inference_workers"), "inference_workers", 1)
    if result.get("error") is not None:
        raise ValueError("result.error 必须为空")
    ranges = _ranges(result.get("sunset_ranges"))
    samples = _samples(root.get("sample_scores"))
    stored = StoredScore(
        application_version=application_version,
        image_count=_integer(result.get("image_count"), "image_count", 0),
        sampled_count=_integer(result.get("sampled_count"), "sampled_count", 1),
        successful_count=_integer(
            result.get("successful_count"), "successful_count", 1
        ),
        failed_count=_integer(result.get("failed_count"), "failed_count", 0),
        interval=_integer(result.get("interval"), "interval", 1),
        average_score=_number(result.get("average_score"), "average_score"),
        max_score=_integer(result.get("max_score"), "max_score", 0, 5),
        has_sunset=_boolean(result.get("has_sunset"), "has_sunset"),
        sunset_ranges=ranges,
        samples=samples,
    )
    _validate_aggregate(stored)
    return stored


def _validate_aggregate(stored: StoredScore) -> None:
    if stored.sampled_count != stored.successful_count + stored.failed_count:
        raise ValueError("采样数与成功、失败数不一致")
    if stored.image_count < stored.sampled_count:
        raise ValueError("图片总数小于采样数")
    if stored.successful_count != len(stored.samples):
        raise ValueError("成功数与逐样本结果数不一致")
    indexes = [sample.sample_index for sample in stored.samples]
    if indexes != sorted(set(indexes)) or indexes[-1] > stored.sampled_count:
        raise ValueError("sample_index 必须有序、唯一且位于采样范围内")
    expected = summarize(stored.samples, stored.sampled_count)
    actual = (
        stored.average_score,
        stored.max_score,
        stored.has_sunset,
        stored.sunset_ranges,
    )
    if actual != expected:
        raise ValueError("聚合结论与逐样本结果不一致")


def _samples(value: Any) -> tuple[SampleScore, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("sample_scores 必须是非空数组")
    samples = []
    for value_item in value:
        item = _mapping(value_item, "sample_score")
        samples.append(
            SampleScore(
                sample_index=_integer(item.get("sample_index"), "sample_index", 1),
                photo=_text(item.get("photo"), "photo"),
                score=_integer(item.get("score"), "score", 0, 5),
                reason=_text(item.get("reason"), "reason"),
            )
        )
    return tuple(samples)


def _ranges(value: Any) -> tuple[SunsetRange, ...]:
    if not isinstance(value, list):
        raise ValueError("sunset_ranges 必须是数组")
    ranges = []
    for value_item in value:
        item = _mapping(value_item, "sunset_range")
        ranges.append(
            SunsetRange(
                start_photo=_text(item.get("start_photo"), "start_photo"),
                end_photo=_text(item.get("end_photo"), "end_photo"),
            )
        )
    return tuple(ranges)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} 必须是对象")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} 必须是非空字符串")
    return value


def _integer(value: Any, name: str, minimum: int, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} 必须是大于等于 {minimum} 的整数")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} 必须小于等于 {maximum}")
    return value


def _number(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not 0 <= value <= 5:
        raise ValueError(f"{name} 必须是 0 到 5 之间的数字")
    return float(value)


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} 必须是布尔值")
    return value
