"""Client for SunsetScore's public persistent JSONL CLI."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from timelapse_manager.errors import ProcessError
from timelapse_manager.sunset_score.jsonl_protocol import (
    PendingRequest,
    PROTOCOL_VERSION,
    SunsetScoreProtocolError,
    decode_event,
    encode_request,
    format_scan_response,
    ready_error,
)

if TYPE_CHECKING:
    from timelapse_manager.child_process import ManagedChild
    from timelapse_manager.runtime import TaskRuntime


class SunsetScoreJsonlClient:
    def __init__(
        self,
        runtime: TaskRuntime,
        command: tuple[str, ...],
        *,
        interval: int,
        application_version: str,
    ) -> None:
        self.runtime = runtime
        self.argv = [*command, "--serve-jsonl", "--interval", str(interval)]
        self.application_version = application_version
        self._condition = threading.Condition()
        self._start_lock = threading.Lock()
        self._child: ManagedChild | None = None
        self._ready = False
        self._disabled_reason = ""
        self._next_id = 1
        self._pending: dict[int, PendingRequest] = {}
        self._responses: dict[int, dict[str, Any]] = {}

    def scan(self, session_id: str, directory: Path) -> None:
        self._send(
            "scan",
            session_id=session_id,
            directory=str(directory.resolve()),
            wait=False,
        )

    def finalize(self, session_id: str) -> Path:
        response = self._send("finalize", session_id=session_id, wait=True)
        assert response is not None
        if response.get("event") == "error":
            raise SunsetScoreProtocolError(str(response.get("error") or "未知错误"))
        if response.get("event") != "finalized":
            raise SunsetScoreProtocolError("SunsetScore 返回了无效 finalize 响应")
        value = response.get("score_file")
        if not isinstance(value, str) or not value:
            raise SunsetScoreProtocolError("SunsetScore 未返回评分文件路径")
        return Path(value)

    def close(self) -> None:
        child = self._child
        if child is None or child.poll() is not None:
            return
        try:
            self._send("close", wait=True)
            child.wait(timeout=5)
        except (ProcessError, subprocess.TimeoutExpired):
            child.terminate()

    def _send(
        self,
        command: str,
        *,
        session_id: str | None = None,
        directory: str | None = None,
        wait: bool,
    ) -> dict[str, Any] | None:
        child = self._ensure_started()
        with self._condition:
            request_id = self._next_id
            self._next_id += 1
            self._pending[request_id] = PendingRequest(command, session_id)
        try:
            child.write_line(
                encode_request(
                    request_id,
                    command,
                    session_id=session_id,
                    directory=directory,
                )
            )
        except ProcessError as exc:
            self._disable(str(exc))
            raise SunsetScoreProtocolError(str(exc)) from exc
        if not wait:
            return None
        return self._wait_for_response(request_id)

    def _ensure_started(self) -> ManagedChild:
        if self._disabled_reason:
            raise SunsetScoreProtocolError(self._disabled_reason)
        with self._start_lock:
            if self._child is None:
                self._child = self.runtime.spawn(
                    "sunsetscore-resident",
                    self.argv,
                    extra_env={"PYTHONUNBUFFERED": "1"},
                    on_line=self._handle_line,
                    writable=True,
                )
            child = self._child
            timeout = max(
                5.0, float(self.runtime.runtime_options["startup_probe_seconds"])
            )
            deadline = time.monotonic() + timeout
            while not self._ready:
                if self._disabled_reason:
                    raise SunsetScoreProtocolError(self._disabled_reason)
                if self.runtime.hard_stop.is_set():
                    raise SunsetScoreProtocolError("任务已停止")
                code = child.poll()
                if code is not None:
                    reason = f"SunsetScore 常驻服务启动失败，退出码={code}"
                    self._disable(reason)
                    raise SunsetScoreProtocolError(reason)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = f"SunsetScore 常驻服务在 {timeout:g} 秒内未就绪"
                    self._disable(reason)
                    child.terminate()
                    raise SunsetScoreProtocolError(reason)
                with self._condition:
                    self._condition.wait(timeout=min(self.runtime.poll_interval, remaining))
            return child

    def _wait_for_response(self, request_id: int) -> dict[str, Any]:
        child = self._child
        assert child is not None
        while True:
            with self._condition:
                response = self._responses.pop(request_id, None)
                if response is not None:
                    return response
                self._condition.wait(timeout=self.runtime.poll_interval)
            if self.runtime.hard_stop.is_set():
                raise SunsetScoreProtocolError("任务已停止")
            code = child.poll()
            if code is not None:
                reason = f"SunsetScore 常驻服务意外退出，退出码={code}"
                self._disable(reason)
                raise SunsetScoreProtocolError(reason)

    def _handle_line(self, line: str) -> None:
        value = decode_event(line)
        if value is None:
            return
        with self._condition:
            if value.get("event") == "ready":
                self._accept_ready(value)
                self._condition.notify_all()
                return
            request_id = value.get("id")
            if type(request_id) is not int:
                return
            pending = self._pending.pop(request_id, None)
            if pending is None:
                return
            if pending.command == "scan":
                message = format_scan_response(pending.session_id, value)
                if message is not None:
                    self.runtime.log(message)
            else:
                self._responses[request_id] = value
            self._condition.notify_all()

    def _accept_ready(self, value: dict[str, Any]) -> None:
        error = ready_error(value, self.application_version)
        if error:
            self._disable(error)
            return
        self._ready = True
        self.runtime.log(
            f"SunsetScore 常驻服务已就绪：协议 {PROTOCOL_VERSION}，"
            f"版本 {self.application_version}"
        )

    def _disable(self, reason: str) -> None:
        if not self._disabled_reason:
            self._disabled_reason = reason
            self.runtime.log(f"SunsetScore 常驻服务不可用：{reason}")
        with self._condition:
            self._condition.notify_all()
