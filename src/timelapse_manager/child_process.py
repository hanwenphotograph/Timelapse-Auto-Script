"""Managed external subprocess with line-based output monitoring."""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

from timelapse_manager.errors import ProcessError
from timelapse_manager.process_utils import (
    child_creation_flags,
    format_command,
    process_identity,
    terminate_tree,
)


class ManagedChild:
    def __init__(
        self,
        role: str,
        argv: list[str],
        *,
        cwd: Path | None,
        env: dict[str, str],
        log: Callable[[str], None],
        on_line: Callable[[str], None] | None,
        on_started: Callable[["ManagedChild"], None],
        on_exited: Callable[["ManagedChild", int], None],
        stop_timeout: float,
    ):
        self.role = role
        self.argv = list(argv)
        self.cwd = cwd
        self.env = env
        self.log = log
        self.on_line = on_line
        self.on_started = on_started
        self.on_exited = on_exited
        self.stop_timeout = stop_timeout
        self.process: subprocess.Popen[str] | None = None
        self.created_at: float | None = None
        self._reader: threading.Thread | None = None
        self._exit_reported = False
        self._terminate_lock = threading.Lock()

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process else None

    @property
    def command_text(self) -> str:
        return format_command(self.argv)

    def start(self) -> "ManagedChild":
        self.log(f"启动 {self.role}: {self.command_text}")
        try:
            self.process = subprocess.Popen(
                self.argv,
                cwd=str(self.cwd) if self.cwd else None,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=child_creation_flags(),
                start_new_session=os.name != "nt",
                close_fds=True,
            )
        except OSError as exc:
            raise ProcessError(f"无法启动 {self.role}: {exc}") from exc
        self.created_at = process_identity(self.process.pid)
        self.on_started(self)
        self._reader = threading.Thread(
            target=self._read_output,
            name=f"output-{self.role}-{self.process.pid}",
            daemon=True,
        )
        self._reader.start()
        return self

    def _read_output(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        try:
            for raw_line in self.process.stdout:
                line = raw_line.rstrip("\r\n")
                self.log(f"[{self.role}] {line}")
                if self.on_line:
                    try:
                        self.on_line(line)
                    except (
                        Exception
                    ) as exc:  # output parsing must never kill the reader
                        self.log(f"{self.role} 输出解析警告: {exc}")
        finally:
            self.process.stdout.close()

    def poll(self) -> int | None:
        if not self.process:
            return None
        code = self.process.poll()
        if code is not None:
            self._report_exit(code)
        return code

    def wait(self, timeout: float | None = None) -> int:
        if not self.process:
            raise ProcessError(f"{self.role} 尚未启动")
        code = self.process.wait(timeout=timeout)
        if self._reader:
            self._reader.join(timeout=2)
        self._report_exit(code)
        return code

    def _report_exit(self, code: int) -> None:
        if self._exit_reported:
            return
        self._exit_reported = True
        self.on_exited(self, code)
        self.log(f"{self.role} 已退出，退出码={code}")

    def terminate(self) -> None:
        with self._terminate_lock:
            if not self.process or self.process.poll() is not None:
                return
            self.log(f"正在停止 {self.role}, PID={self.process.pid}")
            terminate_tree(self.process.pid, self.stop_timeout)
            try:
                self.wait(timeout=2)
            except (subprocess.TimeoutExpired, ProcessError):
                pass
