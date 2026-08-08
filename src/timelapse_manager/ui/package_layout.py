"""Build the package-management page layout."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import customtkinter as ctk

from timelapse_manager.dependency_manager.models import DependencyStatus
from timelapse_manager.ui.package_widgets import DependencyRow
from timelapse_manager.ui.theme import (
    ACCENT,
    BORDER,
    FONT_FAMILY,
    MUTED,
    SURFACE,
    TEXT,
)


@dataclass(frozen=True)
class PackageLayout:
    summary: ctk.CTkLabel
    install_location: ctk.CTkLabel
    activity: ctk.CTkLabel
    refresh_button: ctk.CTkButton
    progress: ctk.CTkProgressBar
    progress_value: ctk.CTkLabel
    rows: dict[str, DependencyRow]


def build_package_layout(
    page: ctk.CTkFrame,
    statuses: list[DependencyStatus],
    dependency_root: str,
    refresh: Callable[[], None],
    install: Callable[[str], None],
) -> PackageLayout:
    page.grid_rowconfigure(1, weight=1)
    page.grid_columnconfigure(0, weight=1)
    toolbar = ctk.CTkFrame(
        page,
        fg_color=SURFACE,
        corner_radius=8,
        border_width=1,
        border_color=BORDER,
    )
    toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
    toolbar.grid_columnconfigure(1, weight=1)
    summary = ctk.CTkLabel(
        toolbar,
        text="等待依赖检测",
        text_color=TEXT,
        font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
        anchor="w",
    )
    summary.grid(row=0, column=0, padx=(16, 18), pady=(11, 2), sticky="w")
    install_location = ctk.CTkLabel(
        toolbar,
        text=f"私有安装目录：{dependency_root}",
        text_color=MUTED,
        font=ctk.CTkFont(family=FONT_FAMILY, size=10),
        anchor="w",
        justify="left",
        wraplength=620,
    )
    install_location.grid(row=1, column=0, columnspan=2, padx=16, sticky="ew")
    activity = ctk.CTkLabel(
        toolbar,
        text="",
        text_color=MUTED,
        font=ctk.CTkFont(family=FONT_FAMILY, size=10),
        anchor="e",
    )
    activity.grid(row=0, column=1, columnspan=2, padx=12, pady=(11, 2), sticky="ew")
    refresh_button = ctk.CTkButton(
        toolbar,
        text="重新检测",
        command=refresh,
        width=94,
        height=32,
        corner_radius=8,
        fg_color=ACCENT,
        font=ctk.CTkFont(family=FONT_FAMILY, size=11),
    )
    refresh_button.grid(row=0, column=3, rowspan=3, padx=14, pady=10)
    progress = ctk.CTkProgressBar(toolbar, height=4, mode="determinate")
    progress.grid(
        row=2, column=0, columnspan=2, sticky="ew", padx=(16, 8), pady=(5, 10)
    )
    progress.set(0)
    progress_value = ctk.CTkLabel(
        toolbar,
        text="0%",
        width=42,
        text_color=MUTED,
        font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
        anchor="e",
    )
    progress_value.grid(row=2, column=2, padx=(0, 6), pady=(2, 7), sticky="e")
    rows = _build_dependency_list(page, statuses, install)
    return PackageLayout(
        summary,
        install_location,
        activity,
        refresh_button,
        progress,
        progress_value,
        rows,
    )


def _build_dependency_list(
    page: ctk.CTkFrame,
    statuses: list[DependencyStatus],
    install: Callable[[str], None],
) -> dict[str, DependencyRow]:
    listing = ctk.CTkScrollableFrame(
        page,
        fg_color=SURFACE,
        corner_radius=8,
        border_width=1,
        border_color=BORDER,
        scrollbar_button_color=BORDER,
        scrollbar_button_hover_color=ACCENT,
    )
    listing.grid(row=1, column=0, sticky="nsew")
    listing.grid_columnconfigure(0, weight=1)
    rows: dict[str, DependencyRow] = {}
    row_index = 0
    current_group = ""
    for status in statuses:
        if status.spec.group != current_group:
            current_group = status.spec.group
            ctk.CTkLabel(
                listing,
                text=current_group,
                text_color=MUTED,
                font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
                anchor="w",
            ).grid(row=row_index, column=0, sticky="ew", padx=16, pady=(14, 3))
            row_index += 1
        row = DependencyRow(listing, status.spec, install)
        row.grid(row=row_index, column=0, sticky="ew")
        rows[status.spec.identifier] = row
        row_index += 1
    return rows
