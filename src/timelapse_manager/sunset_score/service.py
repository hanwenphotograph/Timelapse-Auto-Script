"""Run SunsetScore and apply its notification and retention decision."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import TYPE_CHECKING

from timelapse_manager.errors import ProcessError
from timelapse_manager.sunset_score.availability import (
    SunsetScoreAvailability,
    detect_sunset_score,
)
from timelapse_manager.sunset_score.cache import (
    CacheMismatchError,
    validate_score_inventory,
)
from timelapse_manager.sunset_score.decision import apply_score_result, fail_score
from timelapse_manager.sunset_score.jsonl_client import SunsetScoreJsonlClient
from timelapse_manager.sunset_score.models import SunsetScoreDecision
from timelapse_manager.sunset_score.score_file import (
    SCORE_FILENAME,
    ScoreFileError,
    read_score_file,
)
from timelapse_manager.sunset_score.streaming import StreamingScoreSession

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
        self._session_lock = threading.Lock()
        self._session_sequence = 0
        self._client = None
        if self.availability.enabled:
            assert self.availability.version is not None
            self._client = SunsetScoreJsonlClient(
                runtime,
                self.availability.command,
                interval=interval,
                application_version=self.availability.version,
            )
        self._log_availability()

    @property
    def enabled(self) -> bool:
        return self.availability.enabled

    def start_stream(self, work_dir: Path, label: str) -> StreamingScoreSession | None:
        if not self.enabled or self._client is None:
            return None
        with self._session_lock:
            self._session_sequence += 1
            session_id = f"{self.runtime.task_id}-{self._session_sequence}"
        return StreamingScoreSession(
            self, self._client, session_id, work_dir, label
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

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
        return apply_score_result(
            self.runtime, work_dir, label, hdr_dir, result, highest_path
        )

    def apply_score_file(
        self, work_dir: Path, label: str, score_path: Path
    ) -> SunsetScoreDecision:
        hdr_dir = work_dir / "hdr_enfuse"
        expected = hdr_dir / SCORE_FILENAME
        if score_path.expanduser().resolve() != expected.resolve():
            self._fail(label, f"SunsetScore 返回了意外评分文件路径：{score_path}")
        try:
            result = read_score_file(expected)
        except ScoreFileError as exc:
            self._fail(label, str(exc))
        assert self.availability.version is not None
        try:
            highest_path = validate_score_inventory(
                result,
                hdr_dir,
                interval=self.interval,
                application_version=self.availability.version,
                require_retry_safe=False,
            )
        except CacheMismatchError as exc:
            self._fail(label, str(exc))
        return apply_score_result(
            self.runtime, work_dir, label, hdr_dir, result, highest_path
        )

    def _log_availability(self) -> None:
        if self.enabled:
            command = self.availability.command[0]
            self.runtime.log(
                f"晚霞评分已自动启用：命令 {command}，版本 {self.availability.version}"
            )
        else:
            self.runtime.log(f"晚霞评分未启用：{self.availability.reason}")

    def _fail(self, label: str, reason: str) -> None:
        fail_score(self.runtime, label, reason)
