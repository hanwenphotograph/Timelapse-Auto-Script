"""Reusable modern GUI widgets."""

from __future__ import annotations

import customtkinter as ctk

from timelapse_manager.ui.theme import (
    BORDER,
    FONT_FAMILY,
    MUTED,
    SURFACE,
    TEXT,
)


class SummaryCard(ctk.CTkFrame):
    def __init__(
        self,
        parent: object,
        title: str,
        subtitle: str,
        accent: str,
    ) -> None:
        super().__init__(
            parent,
            fg_color=SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(
            self,
            width=5,
            height=48,
            corner_radius=4,
            fg_color=accent,
        ).grid(row=0, column=0, rowspan=2, sticky="w", padx=(16, 0), pady=18)
        self.value_label = ctk.CTkLabel(
            self,
            text="0",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=27, weight="bold"),
            anchor="w",
        )
        self.value_label.grid(row=0, column=1, sticky="sw", padx=(14, 16), pady=(14, 0))
        ctk.CTkLabel(
            self,
            text=title,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            anchor="w",
        ).grid(row=0, column=2, sticky="sw", padx=(0, 16), pady=(14, 1))
        ctk.CTkLabel(
            self,
            text=subtitle,
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            anchor="w",
        ).grid(row=1, column=1, columnspan=2, sticky="nw", padx=(14, 16), pady=(0, 14))
        self.grid_columnconfigure(2, weight=1)

    def set_value(self, value: int | str) -> None:
        self.value_label.configure(text=str(value))


def action_button(
    parent: object,
    text: str,
    command: object,
    *,
    primary: bool = False,
    danger: bool = False,
    width: int = 92,
) -> ctk.CTkButton:
    if primary:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        )
    if danger:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            fg_color="transparent",
            hover_color=("#FDECEC", "#442129"),
            text_color=("#B42318", "#FF9A9A"),
            border_width=1,
            border_color=("#F3B9B5", "#743742"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        )
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        width=width,
        fg_color="transparent",
        hover_color=("#E9EFFA", "#21304A"),
        text_color=TEXT,
        border_width=1,
        border_color=BORDER,
        font=ctk.CTkFont(family=FONT_FAMILY, size=12),
    )
