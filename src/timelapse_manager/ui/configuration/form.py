"""Reusable typed form that retains unexposed and extension configuration keys."""

from __future__ import annotations

import math
import tkinter as tk
from copy import deepcopy
from tkinter import filedialog

import customtkinter as ctk

from timelapse_manager.errors import ConfigError
from timelapse_manager.ui.configuration.fields import MODE_LABELS
from timelapse_manager.ui.theme import ACCENT, FONT_FAMILY, MUTED, SURFACE, TEXT


def read_path(data, path):
    for part in path.split("."):
        data = data[part]
    return data


def write_path(data, path, value):
    *parents, key = path.split(".")
    for part in parents:
        data = data.setdefault(part, {})
    data[key] = value


def parse_field(field, value):
    if field.kind == "mode":
        return MODE_LABELS[value]
    if field.kind in {"int", "float"}:
        try:
            number = int(value) if field.kind == "int" else float(value)
            if not math.isfinite(number):
                raise ValueError
            return number
        except (ValueError, TypeError, OverflowError) as exc:
            suffix = "整数" if field.kind == "int" else "数字"
            raise ConfigError(f"{field.label}必须是有效的{suffix}") from exc
    return value if field.kind in {"bool", "multiline"} else value.strip()


class ConfigForm(ctk.CTkScrollableFrame):
    def __init__(self, parent, groups):
        super().__init__(parent, fg_color=SURFACE, corner_radius=14)
        self.grid_columnconfigure(1, weight=1)
        self.fields = {}
        self.controls = {}
        self.base = {}
        row = 0
        for title, fields in groups:
            ctk.CTkLabel(
                self,
                text=title,
                text_color=TEXT,
                font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
                anchor="w",
            ).grid(row=row, column=0, columnspan=3, sticky="ew", padx=16, pady=(18, 10))
            row += 1
            for field in fields:
                ctk.CTkLabel(self, text=field.label, text_color=TEXT, anchor="w").grid(
                    row=row, column=0, sticky="nw", padx=16, pady=9
                )
                control = self._control(field)
                control.grid(row=row, column=1, sticky="ew", padx=12, pady=6)
                self.fields[field.path] = field
                self.controls[field.path] = control
                if field.kind == "directory":
                    ctk.CTkButton(
                        self,
                        text="浏览",
                        width=64,
                        command=lambda p=field.path: self._browse(p),
                    ).grid(row=row, column=2, padx=(0, 16), pady=6)
                row += 1
        if "photo_processing.mode" in self.controls:
            ctk.CTkLabel(
                self,
                text="自定义时间：素材先下载保存，每天按本机时间集中处理；新素材等待下一次开始时间。\n"
                "保存后，待处理队列使用新的开始时间；拍摄模式与其他参数在下次任务启动时生效。",
                text_color=MUTED,
                anchor="w",
                justify="left",
                wraplength=650,
            ).grid(row=row, column=0, columnspan=3, sticky="ew", padx=16, pady=16)

    def _control(self, field):
        if field.kind == "bool":
            return ctk.CTkSwitch(self, text="", onvalue=True, offvalue=False)
        if field.kind == "mode":
            return ctk.CTkSegmentedButton(
                self,
                values=list(MODE_LABELS),
                selected_color=ACCENT,
                command=self._mode_changed,
            )
        if field.kind == "multiline":
            return ctk.CTkTextbox(self, height=100, wrap="word")
        return ctk.CTkEntry(self, height=34)

    def load(self, data):
        self.base = deepcopy(data)
        for path, field in self.fields.items():
            control = self.controls[path]
            value = read_path(data, path)
            if field.kind == "bool":
                control.select() if value else control.deselect()
            elif field.kind == "mode":
                control.set(
                    next(label for label, mode in MODE_LABELS.items() if mode == value)
                )
            else:
                # A previous immediate-mode load may have disabled the time entry.
                control.configure(state="normal")
                start = "1.0" if field.kind == "multiline" else 0
                control.delete(start, tk.END)
                control.insert(start, str(value))
        self._mode_changed()

    def values(self):
        data = deepcopy(self.base)
        for path, field in self.fields.items():
            control = self.controls[path]
            value = (
                control.get("1.0", "end-1c")
                if field.kind == "multiline"
                else control.get()
            )
            write_path(data, path, parse_field(field, value))
        return data

    def _mode_changed(self, _value=None):
        if "photo_processing.start_at" in self.controls:
            state = (
                "normal"
                if self.controls["photo_processing.mode"].get() == "自定义时间"
                else "disabled"
            )
            self.controls["photo_processing.start_at"].configure(state=state)

    def _browse(self, path):
        directory = filedialog.askdirectory(parent=self, title="选择目录")
        if directory:
            control = self.controls[path]
            control.delete(0, tk.END)
            control.insert(0, directory)
