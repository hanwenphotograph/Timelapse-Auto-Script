"""Application icon loading for Tk windows."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path


ICON_NAME = "timelapse-manager.png"


def application_icon_path() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        bundled = Path(frozen_root) / "timelapse_manager" / "assets" / ICON_NAME
        if bundled.is_file():
            return bundled
    return Path(__file__).with_name("assets") / ICON_NAME


def apply_application_icon(root: tk.Tk) -> None:
    icon_path = application_icon_path()
    try:
        photo = tk.PhotoImage(master=root, file=str(icon_path))
        root.iconphoto(True, photo)
        root._timelapse_icon_photo = photo  # type: ignore[attr-defined]
    except (OSError, tk.TclError):
        pass
