"""Run SunsetScore and apply its notification and retention decision."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from timelapse_manager.errors import ProcessError, TaskError
from timelapse_manager.sunset_score.availability import (
    SunsetScoreAvailability,
    detect_sunset_score,
)
from timelapse_manager.sunset_score.cache import (
    CacheMismatchError,
    validate_score_inventory,
)
from timelapse_manager.sunset_score.models import SunsetScoreDecision
from timelapse_manager.sunset_score.score_file import (
    SCORE_FILENAME,
    ScoreFileError,
    read_score_file,
)

if TYPE_CHECKING:
    from timelapse_manager.runtime import TaskRuntime


class SunsetScoreService:
    def __init__(
        self,
        runtime: TaskRuntime,
        command_value: str,
        interval: int,
        *,
        processing_enabled: bool,
    ):
        self.runtime = runtime
        self.interval = interval
        if processing_enabled:
            self.availability = detect_sunset_score(command_value)
        else:
            self.availability = SunsetScoreAvailability(reason="任务未启用后期处理")
        self._log_availability()

    @property
    def enabled(self) -> bool:
        return self.availability.enabled

    def process(self, work_dir: Path, label: str) -> SunsetScoreDecision | None:
        if not self.enabled:
            return None
        hdr_dir = work_dir / "hdr_enfuse"
        if not hdr_dir.is_dir() or hdr_dir.is_symlink():
            self._fail(label, f"HDR 目录不存在或不安全：{hdr_dir}")
        self.runtime.set_phase("晚霞评分", f"{label}，目录 {hdr_dir}")

        assert self.availability.version is not None
        score_path = hdr_dir / SCORE_FILENAME
        result = None
        highest_path = None
        if score_path.exists():
            try:
                result = read_score_file(score_path)
                highest_path = validate_score_inventory(
                    result,
                    hdr_dir,
                    interval=self.interval,
                    application_version=self.availability.version,
                    require_retry_safe=True,
                )
                self.runtime.log(f"晚霞评分复用有效缓存：{score_path}")
            except (ScoreFileError, CacheMismatchError) as exc:
                self.runtime.log(f"晚霞评分缓存不可复用，将重新评分：{exc}")
                result = None

        if result is None:
            command = [
                *self.availability.command,
                str(hdr_dir),
                "--interval",
                str(self.interval),
            ]
            if score_path.exists():
                command.append("--force")
            try:
                child = self.runtime.spawn(
                    "sunsetscore",
                    command,
                    cwd=work_dir,
                )
            except ProcessError as exc:
                self._fail(label, str(exc))
            code = self.runtime.wait_child(child)
            if code != 0:
                self._fail(label, f"SunsetScore 退出码为 {code}")
            try:
                result = read_score_file(score_path)
                highest_path = validate_score_inventory(
                    result,
                    hdr_dir,
                    interval=self.interval,
                    application_version=self.availability.version,
                    require_retry_safe=False,
                )
            except (ScoreFileError, CacheMismatchError) as exc:
                self._fail(label, str(exc))

        assert result is not None
        assert highest_path is not None
        if result.failed_count and not result.has_sunset:
            self._fail(
                label,
                f"{result.failed_count} 张采样照片评分失败且未检测到晚霞，结果不足以安全删图",
            )

        action = "保留 hdr_enfuse" if result.has_sunset else "删除 hdr_enfuse"
        summary = self._summary(label, hdr_dir, result, action)
        self.runtime.log(summary)
        self.runtime.webhook.notify("sunset-score-result", summary)
        highest = result.highest
        self.runtime.webhook.notify_image_path(
            "sunset-score-image",
            (
                f"晚霞评分最高分照片：{label}；文件 {highest.photo}；"
                f"评分 {highest.score}/5；理由：{highest.reason}"
            ),
            highest_path,
            work_dir,
        )

        if result.has_sunset:
            self.runtime.log(f"检测到晚霞，保留 HDR 照片目录：{hdr_dir}")
        else:
            try:
                shutil.rmtree(hdr_dir)
            except OSError as exc:
                raise TaskError(f"无法删除无晚霞 HDR 目录 {hdr_dir}：{exc}") from exc
            self.runtime.log(f"未检测到晚霞，已删除 HDR 照片目录：{hdr_dir}")
        return SunsetScoreDecision(result, highest_path, result.has_sunset)

    def _log_availability(self) -> None:
        if self.enabled:
            command = self.availability.command[0]
            self.runtime.log(
                f"晚霞评分已自动启用：命令 {command}，版本 {self.availability.version}"
            )
        else:
            self.runtime.log(f"晚霞评分未启用：{self.availability.reason}")

    def _fail(self, label: str, reason: str) -> None:
        message = f"晚霞评分失败：{label}；{reason}；已保留 HDR 照片"
        self.runtime.log(message)
        self.runtime.webhook.notify("sunset-score-result", message)
        raise TaskError(reason)

    @staticmethod
    def _summary(label: str, hdr_dir: Path, result, action: str) -> str:
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
