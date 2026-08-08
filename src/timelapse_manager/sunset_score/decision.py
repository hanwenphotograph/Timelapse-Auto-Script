"""Apply a stored sunset score to notifications and HDR retention."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import NoReturn, TYPE_CHECKING

from timelapse_manager.errors import TaskError
from timelapse_manager.sunset_score.models import StoredScore, SunsetScoreDecision

if TYPE_CHECKING:
    from timelapse_manager.runtime import TaskRuntime


def apply_score_result(
    runtime: TaskRuntime,
    work_dir: Path,
    label: str,
    hdr_dir: Path,
    result: StoredScore,
    highest_path: Path,
) -> SunsetScoreDecision:
    if result.failed_count and not result.has_sunset:
        fail_score(
            runtime,
            label,
            f"{result.failed_count} 张采样照片评分失败且未检测到晚霞，结果不足以安全删图",
        )

    action = "保留 hdr_enfuse" if result.has_sunset else "删除 hdr_enfuse"
    summary = _summary(label, hdr_dir, result, action)
    runtime.log(summary)
    runtime.webhook.notify("sunset-score-result", summary)
    highest = result.highest
    runtime.webhook.notify_image_path(
        "sunset-score-image",
        (
            f"晚霞评分最高分照片：{label}；文件 {highest.photo}；"
            f"评分 {highest.score}/5；理由：{highest.reason}"
        ),
        highest_path,
        work_dir,
    )

    if result.has_sunset:
        runtime.log(f"检测到晚霞，保留 HDR 照片目录：{hdr_dir}")
    else:
        try:
            shutil.rmtree(hdr_dir)
        except OSError as exc:
            raise TaskError(f"无法删除无晚霞 HDR 目录 {hdr_dir}：{exc}") from exc
        runtime.log(f"未检测到晚霞，已删除 HDR 照片目录：{hdr_dir}")
    return SunsetScoreDecision(result, highest_path, result.has_sunset)


def fail_score(runtime: TaskRuntime, label: str, reason: str) -> NoReturn:
    message = f"晚霞评分失败：{label}；{reason}；已保留 HDR 照片"
    runtime.log(message)
    runtime.webhook.notify("sunset-score-result", message)
    raise TaskError(reason)


def _summary(label: str, hdr_dir: Path, result: StoredScore, action: str) -> str:
    ranges = (
        "-"
        if not result.sunset_ranges
        else "；".join(
            item.start_photo
            if item.start_photo == item.end_photo
            else f"{item.start_photo} 至 {item.end_photo}"
            for item in result.sunset_ranges
        )
    )
    return (
        f"晚霞评分结果：{label}；目录 {hdr_dir}；照片 {result.image_count} 张；"
        f"采样间隔 {result.interval}；采样 {result.sampled_count} 张"
        f"（成功 {result.successful_count}，失败 {result.failed_count}）；"
        f"平均分 {result.average_score:.2f}；最高分 {result.max_score}/5；"
        f"检测到晚霞：{'是' if result.has_sunset else '否'}；"
        f"晚霞区间：{ranges}；处理动作：{action}"
    )
