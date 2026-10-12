"""Camera connection status with a nonblocking, manually refreshed probe."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue

import customtkinter as ctk

from timelapse_manager.camera import CameraConnection, detect_connection
from timelapse_manager.ui.theme import (
    BORDER,
    DANGER,
    FONT_FAMILY,
    MUTED,
    SUCCESS,
    SURFACE,
    TEXT,
    WARNING,
)
from timelapse_manager.ui.widgets import action_button


STATE_STYLE = {
    "connected": ("相机已连接", SUCCESS),
    "disconnected": ("相机未连接", WARNING),
    "unavailable": ("检测不可用", WARNING),
    "error": ("检测失败", DANGER),
}


class CameraStatusPanel(ctk.CTkFrame):
    def __init__(self, parent: object, root_path: Path) -> None:
        super().__init__(
            parent,
            fg_color=SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        self.root_path = root_path
        self._results: Queue[CameraConnection] = Queue()
        self._busy = False
        self._closed = False
        self._poll_id: str | None = None
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self,
            text="相机连接",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=13, pady=(10, 0))
        self.state_label = ctk.CTkLabel(
            self,
            text="尚未检测",
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
        )
        self.state_label.grid(row=1, column=0, sticky="ew", padx=13)
        self.detail_label = ctk.CTkLabel(
            self,
            text="",
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=166,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
        )
        self.detail_label.grid(row=2, column=0, sticky="ew", padx=13)
        self.checked_label = ctk.CTkLabel(
            self,
            text="",
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
        )
        self.checked_label.grid(row=3, column=0, sticky="ew", padx=13)
        self.refresh_button = action_button(self, "刷新相机", self.refresh)
        self.refresh_button.grid(row=4, column=0, sticky="ew", padx=10, pady=(4, 10))
        self._poll_id = self.after(0, self.refresh)

    def refresh(self) -> None:
        if self._closed or self._busy:
            return
        self._busy = True
        self.refresh_button.configure(state="disabled")
        self.state_label.configure(text="检测中…", text_color=MUTED)
        self.detail_label.configure(text="正在检查相机连接")

        def work() -> None:
            try:
                connection = detect_connection(self.root_path)
            except Exception as exc:
                connection = CameraConnection("error", f"相机检测失败：{exc}")
            self._results.put(connection)

        threading.Thread(target=work, name="camera-connection", daemon=True).start()
        self._poll_id = self.after(100, self._poll_result)

    def _poll_result(self) -> None:
        self._poll_id = None
        if self._closed:
            return
        try:
            connection = self._results.get_nowait()
        except Empty:
            self._poll_id = self.after(100, self._poll_result)
            return
        self._busy = False
        self.refresh_button.configure(state="normal")
        label, color = STATE_STYLE[connection.status]
        if len(connection.devices) > 1:
            label += f" · {len(connection.devices)} 台"
        self.state_label.configure(text=label, text_color=color)
        self.detail_label.configure(text=connection.message)
        checked = (
            datetime.fromisoformat(connection.checked_at)
            if connection.checked_at
            else datetime.now()
        )
        self.checked_label.configure(text=f"最近检测 {checked:%H:%M:%S}")

    def close(self) -> None:
        self._closed = True
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None
