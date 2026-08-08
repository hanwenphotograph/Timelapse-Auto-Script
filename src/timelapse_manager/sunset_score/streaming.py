"""One directory session in SunsetScore's public persistent service."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from timelapse_manager.errors import ProcessError, TaskError

if TYPE_CHECKING:
    from timelapse_manager.sunset_score.jsonl_client import SunsetScoreJsonlClient
    from timelapse_manager.sunset_score.service import SunsetScoreService


class StreamingScoreSession:
    def __init__(
        self,
        service: SunsetScoreService,
        client: SunsetScoreJsonlClient,
        session_id: str,
        work_dir: Path,
        label: str,
    ):
        self.service = service
        self.client = client
        self.session_id = session_id
        self.work_dir = work_dir
        self.hdr_dir = work_dir / "hdr_enfuse"
        self.label = label

    def scan(self) -> None:
        if not self.hdr_dir.is_dir():
            return
        self.client.scan(self.session_id, self.hdr_dir)
        self.service.runtime.log(f"晚霞增量扫描已提交：{self.label}")

    def finish(self):
        if not self.hdr_dir.is_dir() or self.hdr_dir.is_symlink():
            raise TaskError(f"HDR 目录不存在或不安全：{self.hdr_dir}")
        try:
            self.scan()
            score_path = self.client.finalize(self.session_id)
        except ProcessError as exc:
            self.service._fail(self.label, str(exc))
        return self.service.apply_score_file(self.work_dir, self.label, score_path)
