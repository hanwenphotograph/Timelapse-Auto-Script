"""Graphical entry point for the headless Timelapse Manager service."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from timelapse_manager.app_icon import (
    apply_application_icon,
    prepare_application_icon,
)
from timelapse_manager.service import ManagerService
from timelapse_manager.ui.app import TimelapseApp
from timelapse_manager.ui.theme import apply_base_theme


def launch_gui(root_path: Path | None = None) -> None:
    reveal_macos_icon = prepare_application_icon()
    apply_base_theme()
    root = ctk.CTk()
    apply_application_icon(root, reveal_macos_icon=reveal_macos_icon)
    service = ManagerService(root_path)
    TimelapseApp(root, service)
    root.mainloop()
