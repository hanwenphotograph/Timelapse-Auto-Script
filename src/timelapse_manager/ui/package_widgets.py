"""Rows used by the package-management page."""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from timelapse_manager.dependency_manager.models import (
    DependencySpec,
    DependencyStatus,
)
from timelapse_manager.ui.theme import (
    BORDER,
    DANGER,
    FONT_FAMILY,
    MUTED,
    SUCCESS,
    SURFACE_ALT,
    TEXT,
    WARNING,
)


STATE_STYLE = {
    "ready": ("已就绪", SUCCESS, ("#E8F7F0", "#123629")),
    "missing": ("未安装", WARNING, ("#FFF4E5", "#3A2A10")),
    "issue": ("不可用", DANGER, ("#FDECEC", "#442129")),
    "outdated": ("需更新", DANGER, ("#FDECEC", "#442129")),
    "checking": ("检测中", MUTED, SURFACE_ALT),
}


class DependencyRow(ctk.CTkFrame):
    def __init__(
        self,
        parent: object,
        spec: DependencySpec,
        action: Callable[[str], None],
    ) -> None:
        super().__init__(parent, fg_color="transparent", corner_radius=0, height=76)
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=4, minsize=245)
        self.grid_columnconfigure(2, weight=5, minsize=280)
        self.spec = spec

        name_pad = (34, 10) if spec.parent_id else (16, 10)
        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.grid(row=0, column=0, sticky="nsew", padx=name_pad, pady=11)
        name_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            name_frame,
            text=spec.name,
            text_color=TEXT,
            font=ctk.CTkFont(
                family=FONT_FAMILY,
                size=12,
                weight="bold" if not spec.parent_id else "normal",
            ),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        requirement = "必需" if spec.required else "可选"
        ctk.CTkLabel(
            name_frame,
            text=f"{requirement} · {spec.description}",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(3, 0))

        self.badge = ctk.CTkLabel(
            self,
            text="检测中",
            width=74,
            height=27,
            corner_radius=6,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
        )
        self.badge.grid(row=0, column=1, padx=10)
        self.detail = ctk.CTkLabel(
            self,
            text="等待检测",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self.detail.grid(row=0, column=2, sticky="ew", padx=10)
        self.button = ctk.CTkButton(
            self,
            text=spec.action_label if spec.action_id else "",
            command=lambda: action(spec.identifier),
            width=104,
            height=32,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
            fg_color="transparent",
            hover_color=SURFACE_ALT,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
        )
        if spec.action_id:
            self.button.grid(row=0, column=3, padx=(10, 16))

        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).grid(
            row=1, column=0, columnspan=4, sticky="sew", padx=16
        )

    def update_status(self, status: DependencyStatus, *, busy: bool) -> None:
        label, color, background = STATE_STYLE[status.state]
        self.badge.configure(text=label, text_color=color, fg_color=background)
        self.detail.configure(text=status.detail)
        if not self.spec.action_id:
            return
        enabled = status.action_available and not busy
        text = self.spec.action_label
        if status.state == "checking":
            text = "检测中"
        elif not status.action_available:
            if status.ready:
                text = "已检测"
            elif self.spec.action_id == "sunset:prepare":
                text = "先装主程序"
            else:
                text = "手动安装"
        self.button.configure(text=text, state="normal" if enabled else "disabled")
