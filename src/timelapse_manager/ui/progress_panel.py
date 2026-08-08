"""CustomTkinter task progress panel."""

from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from timelapse_manager.ui.progress import ProgressItem, task_progress_items
from timelapse_manager.ui.theme import (
    ACCENT,
    BORDER,
    DANGER,
    FONT_FAMILY,
    MUTED,
    SUCCESS,
    SURFACE,
    TEXT,
    WARNING,
)


_STATUS_TEXT = {
    "idle": "未启动",
    "starting": "启动中",
    "running": "运行中",
    "finishing": "收尾中",
    "stopping": "停止中",
    "completed": "已完成",
    "failed": "失败",
    "stopped": "已停止",
    "exited": "已退出",
    "waiting": "等待中",
    "queued": "排队中",
}
_LIST_HEIGHT = 144


class _ProgressRow(ctk.CTkFrame):
    def __init__(self, parent: object) -> None:
        super().__init__(parent, fg_color="transparent", corner_radius=0)
        self.grid_columnconfigure(1, weight=1)
        self.name = ctk.CTkLabel(
            self,
            text="",
            width=205,
            height=32,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            anchor="w",
        )
        self.name.grid(row=0, column=0, rowspan=2, sticky="w", padx=(2, 14))
        self.bar = ctk.CTkProgressBar(
            self,
            height=8,
            corner_radius=4,
            mode="determinate",
            fg_color=BORDER,
            progress_color=ACCENT,
        )
        self.bar.grid(row=0, column=1, sticky="ew", pady=(4, 2))
        self._animating = False
        self.detail = ctk.CTkLabel(
            self,
            text="",
            height=14,
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self.detail.grid(row=1, column=1, sticky="ew")
        self.value = ctk.CTkLabel(
            self,
            text="",
            width=72,
            height=16,
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            anchor="e",
        )
        self.value.grid(row=0, column=2, rowspan=2, sticky="e", padx=(14, 4))

    def set_item(self, item: ProgressItem) -> None:
        self.name.configure(text=item.label)
        self.detail.configure(text=item.detail)
        color = _status_color(item.status)
        self.bar.configure(progress_color=color)
        if item.value is None:
            self.bar.configure(mode="indeterminate")
            animate = item.status in {"starting", "running", "finishing", "stopping"}
            if animate and not self._animating:
                self.bar.set(0)
                self.bar.start()
            elif not animate and self._animating:
                self.bar.stop()
            self._animating = animate
            value_text = _STATUS_TEXT.get(item.status, item.status)
        else:
            if self._animating:
                self.bar.stop()
            self._animating = False
            self.bar.configure(mode="determinate")
            self.bar.set(item.value)
            value_text = f"{item.value:.0%}"
        self.value.configure(text=value_text, text_color=color)

    def destroy(self) -> None:
        self.bar.stop()
        super().destroy()


class TaskProgressPanel(ctk.CTkFrame):
    """Display overall progress first and any number of subtask rows below it."""

    def __init__(self, parent: object) -> None:
        super().__init__(
            parent,
            fg_color=SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        self.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 3))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text="任务进度",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.task_name = ctk.CTkLabel(
            header,
            text="",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            anchor="e",
            justify="right",
            wraplength=520,
        )
        self.task_name.grid(row=0, column=1, sticky="e")
        self.listing = ctk.CTkScrollableFrame(
            self,
            height=_LIST_HEIGHT,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT,
        )
        # The nested scrollbar otherwise keeps its 200 px default request height.
        self.listing._scrollbar.configure(height=_LIST_HEIGHT)
        self.listing.grid(row=1, column=0, sticky="ew", padx=(12, 5), pady=(0, 8))
        self.listing.grid_columnconfigure(0, weight=1)
        self._rows: dict[str, _ProgressRow] = {}

    def show_task(
        self,
        task: dict[str, object],
        state: dict[str, object],
        *,
        now: datetime | None = None,
    ) -> None:
        name = task.get("name") or task.get("id") or ""
        self.task_name.configure(text=str(name))
        items = task_progress_items(task, state, now=now)
        if tuple(item.key for item in items) != tuple(self._rows):
            self._replace_rows(items)
            return
        for item in items:
            self._rows[item.key].set_item(item)

    def clear(self) -> None:
        self.task_name.configure(text="未选择任务")
        self._replace_rows(())

    def _replace_rows(self, items: tuple[ProgressItem, ...]) -> None:
        for row in self._rows.values():
            row.destroy()
        self._rows.clear()
        for index, item in enumerate(items):
            row = _ProgressRow(self.listing)
            top = 0 if index == 0 else 4
            row.grid(row=index, column=0, sticky="ew", pady=(top, 0))
            row.set_item(item)
            self._rows[item.key] = row
        self.listing._parent_canvas.yview_moveto(0)


def _status_color(status: str) -> str:
    if status == "completed":
        return SUCCESS
    if status in {"failed", "stopped", "exited"}:
        return DANGER
    if status in {"finishing", "stopping"}:
        return WARNING
    return ACCENT
