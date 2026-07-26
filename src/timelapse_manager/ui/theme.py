"""Shared colors, fonts, and ttk compatibility styling for the GUI."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk


Color = str | tuple[str, str]

BACKGROUND: Color = ("#F4F7FB", "#080D18")
SIDEBAR: Color = ("#EAF0FA", "#0D1422")
SURFACE: Color = ("#FFFFFF", "#111A2B")
SURFACE_ALT: Color = ("#F7F9FC", "#162235")
BORDER: Color = ("#DDE4EE", "#26344B")
TEXT: Color = ("#172033", "#F2F6FC")
MUTED: Color = ("#64748B", "#92A2B9")
ACCENT = "#3977F6"
ACCENT_HOVER = "#2864DD"
SUCCESS = "#23A36D"
WARNING = "#E49A25"
DANGER = "#E55353"
DANGER_HOVER = "#C94141"


def platform_font_family() -> str:
    if sys.platform == "darwin":
        return "PingFang SC"
    if os.name == "nt":
        return "Microsoft YaHei UI"
    return "Noto Sans CJK SC"


def platform_monospace_font_family() -> str:
    if sys.platform == "darwin":
        return "Menlo"
    if os.name == "nt":
        return "Consolas"
    return "DejaVu Sans Mono"


FONT_FAMILY = platform_font_family()
MONOSPACE_FONT_FAMILY = platform_monospace_font_family()


def apply_base_theme() -> None:
    ctk.set_default_color_theme("blue")
    ctk.set_appearance_mode("System")


def apply_font_defaults(root: tk.Misc) -> None:
    """Use one platform font family for every Tk and CustomTkinter fallback."""
    root.option_add("*Font", f"{{{FONT_FAMILY}}} 10")
    for name in (
        "TkDefaultFont",
        "TkTextFont",
        "TkFixedFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkCaptionFont",
        "TkSmallCaptionFont",
        "TkIconFont",
        "TkTooltipFont",
    ):
        try:
            tkfont.nametofont(name, root=root).configure(family=FONT_FAMILY)
        except tk.TclError:
            continue


def resolved(color: Color) -> str:
    if isinstance(color, str):
        return color
    return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]


def apply_table_style(root: object) -> None:
    """Restyle ttk.Treeview while keeping its accessible table behavior."""
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    background = resolved(SURFACE)
    heading = resolved(SURFACE_ALT)
    foreground = resolved(TEXT)
    muted = resolved(MUTED)
    border = resolved(BORDER)

    style.configure(
        "Modern.Treeview",
        background=background,
        fieldbackground=background,
        foreground=foreground,
        bordercolor=border,
        lightcolor=background,
        darkcolor=background,
        borderwidth=0,
        relief="flat",
        rowheight=42,
        font=(FONT_FAMILY, 12),
    )
    style.configure(
        "Modern.Treeview.Heading",
        background=heading,
        foreground=muted,
        bordercolor=border,
        lightcolor=heading,
        darkcolor=heading,
        relief="flat",
        padding=(8, 9),
        font=(FONT_FAMILY, 11, "bold"),
    )
    style.map(
        "Modern.Treeview",
        background=[("selected", ACCENT)],
        foreground=[("selected", "#FFFFFF")],
    )
    style.map(
        "Modern.Treeview.Heading",
        background=[("active", resolved(BORDER))],
        foreground=[("active", foreground)],
    )


def apply_status_tags(tree: ttk.Treeview) -> None:
    if ctk.get_appearance_mode() == "Dark":
        colors = {
            "running": "#62D5A3",
            "starting": "#76A7FF",
            "finishing": "#F6C76B",
            "stopping": "#F09595",
            "failed": "#FF8A8A",
            "completed": "#8FA5C4",
        }
    else:
        colors = {
            "running": "#087A4B",
            "starting": "#1F5FC7",
            "finishing": "#9A5B00",
            "stopping": "#B43737",
            "failed": "#B42318",
            "completed": "#52647D",
        }
    for status, color in colors.items():
        tree.tag_configure(status, foreground=color)
