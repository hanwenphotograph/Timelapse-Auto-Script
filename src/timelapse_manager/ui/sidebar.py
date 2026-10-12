"""Navigation, camera status, and appearance controls shared by every page."""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from timelapse_manager.ui.camera_status import CameraStatusPanel
from timelapse_manager.ui.theme import (
    ACCENT,
    BORDER,
    FONT_FAMILY,
    MUTED,
    SIDEBAR,
    SURFACE,
    SURFACE_ALT,
    TEXT,
)

if TYPE_CHECKING:
    from timelapse_manager.ui.app import TimelapseApp


def build_sidebar(app: TimelapseApp, mode: str) -> None:
    sidebar = ctk.CTkFrame(
        app.root,
        width=226,
        corner_radius=0,
        fg_color=SIDEBAR,
    )
    sidebar.grid(row=0, column=0, sticky="nsew")
    sidebar.grid_propagate(False)
    sidebar.grid_rowconfigure(2, weight=1)
    sidebar.grid_columnconfigure(0, weight=1)

    brand = ctk.CTkFrame(sidebar, fg_color="transparent")
    brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 28))
    brand.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(
        brand,
        text="TL",
        width=44,
        height=44,
        corner_radius=12,
        fg_color=ACCENT,
        text_color="#FFFFFF",
        font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
    ).grid(row=0, column=0, rowspan=2, sticky="w")
    ctk.CTkLabel(
        brand,
        text="Timelapse",
        text_color=TEXT,
        font=ctk.CTkFont(family=FONT_FAMILY, size=17, weight="bold"),
        anchor="w",
    ).grid(row=0, column=1, sticky="sw", padx=(11, 0))
    ctk.CTkLabel(
        brand,
        text=f"Manager · {mode}",
        text_color=MUTED,
        font=ctk.CTkFont(family=FONT_FAMILY, size=10),
        anchor="w",
    ).grid(row=1, column=1, sticky="nw", padx=(11, 0))

    nav = ctk.CTkFrame(sidebar, fg_color="transparent")
    nav.grid(row=1, column=0, sticky="new", padx=13)
    nav.grid_columnconfigure(0, weight=1)
    nav_items = (
        ("overview", "运行总览"),
        ("tasks", "任务管理"),
        ("processes", "进程监控"),
        ("packages", "包管理"),
        ("config", "配置中心"),
        ("logs", "运行日志"),
    )
    app.nav_buttons: dict[str, ctk.CTkButton] = {}
    for row, (key, label) in enumerate(nav_items):
        button = ctk.CTkButton(
            nav,
            text=f"  {label}",
            command=lambda value=key: app.show_page(value),
            height=42,
            corner_radius=10,
            anchor="w",
            fg_color="transparent",
            hover_color=("#DCE6F7", "#1C2A42"),
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
        )
        button.grid(row=row, column=0, sticky="ew", pady=3)
        app.nav_buttons[key] = button

    app.camera_status = CameraStatusPanel(sidebar, app.service.paths.root)
    app.camera_status.grid(row=2, column=0, sticky="sew", padx=16, pady=(18, 0))

    appearance = ctk.CTkFrame(
        sidebar,
        fg_color=SURFACE,
        corner_radius=12,
        border_width=1,
        border_color=BORDER,
    )
    appearance.grid(row=3, column=0, sticky="sew", padx=16, pady=18)
    appearance.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        appearance,
        text="界面外观",
        text_color=TEXT,
        font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
        anchor="w",
    ).grid(row=0, column=0, sticky="ew", padx=13, pady=(12, 6))
    ctk.CTkOptionMenu(
        appearance,
        values=["跟随系统", "浅色", "深色"],
        variable=app.appearance_value,
        command=app._change_appearance,
        height=32,
        corner_radius=8,
        fg_color=SURFACE_ALT,
        button_color=ACCENT,
        button_hover_color=ACCENT,
        text_color=TEXT,
        font=ctk.CTkFont(family=FONT_FAMILY, size=11),
        dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=11),
    ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
