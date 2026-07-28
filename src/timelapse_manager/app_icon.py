"""Application icon loading for Tk windows and the macOS Dock."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes.util import find_library
from pathlib import Path


ICON_NAME = "timelapse-manager.png"

class _ProcessSerialNumber(ctypes.Structure):
    _fields_ = [
        ("high_long_of_psn", ctypes.c_uint32),
        ("low_long_of_psn", ctypes.c_uint32),
    ]


def application_icon_path() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        bundled = Path(frozen_root) / "timelapse_manager" / "assets" / ICON_NAME
        if bundled.is_file():
            return bundled
    return Path(__file__).with_name("assets") / ICON_NAME


def prepare_application_icon() -> bool:
    if sys.platform != "darwin" or getattr(sys, "frozen", False):
        return False
    return _hide_macos_dock_icon()


def apply_application_icon(root: tk.Tk, *, reveal_macos_icon: bool = False) -> None:
    icon_path = application_icon_path()
    try:
        photo = tk.PhotoImage(master=root, file=str(icon_path))
        root.iconphoto(True, photo)
        root._timelapse_icon_photo = photo  # type: ignore[attr-defined]
    except (OSError, tk.TclError):
        pass
    if sys.platform == "darwin":
        _set_macos_dock_icon(icon_path)
        if reveal_macos_icon:
            _reveal_macos_dock_icon()
            # The Dock creates its tile asynchronously after this policy change.
            _set_macos_dock_icon(icon_path)
            root.after(100, _set_macos_dock_icon, icon_path)


def _hide_macos_dock_icon() -> bool:
    try:
        services_path = find_library("ApplicationServices")
        if not services_path:
            return False
        services = ctypes.CDLL(services_path)
        get_current_process = services.GetCurrentProcess
        get_current_process.argtypes = [ctypes.POINTER(_ProcessSerialNumber)]
        get_current_process.restype = ctypes.c_int32
        transform_process = services.TransformProcessType
        transform_process.argtypes = [
            ctypes.POINTER(_ProcessSerialNumber),
            ctypes.c_uint32,
        ]
        transform_process.restype = ctypes.c_int32
        process = _ProcessSerialNumber()
        if get_current_process(ctypes.byref(process)) != 0:
            return False
        return transform_process(ctypes.byref(process), 4) == 0
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _load_objc_runtime() -> ctypes.CDLL | None:
    objc_path = find_library("objc")
    if not objc_path:
        return None
    objc = ctypes.CDLL(objc_path)
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    return objc


def _reveal_macos_dock_icon() -> bool:
    try:
        objc = _load_objc_runtime()
        if objc is None:
            return False
        send_id = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(("objc_msgSend", objc))
        set_policy = ctypes.CFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_long,
        )(("objc_msgSend", objc))
        application = send_id(
            objc.objc_getClass(b"NSApplication"),
            objc.sel_registerName(b"sharedApplication"),
        )
        if not application:
            return False
        policy_selector = objc.sel_registerName(b"setActivationPolicy:")
        set_policy(application, policy_selector, 1)
        return bool(set_policy(application, policy_selector, 0))
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _set_macos_dock_icon(icon_path: Path) -> bool:
    try:
        appkit_path = find_library("AppKit")
        objc = _load_objc_runtime()
        if objc is None or not appkit_path:
            return False
        ctypes.CDLL(appkit_path)
        send_id = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(("objc_msgSend", objc))
        send_id_arg = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(("objc_msgSend", objc))
        send_text = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_char_p,
        )(("objc_msgSend", objc))
        send_bool_arg = ctypes.CFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(("objc_msgSend", objc))
        send_void_arg = ctypes.CFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(("objc_msgSend", objc))
        send_void = ctypes.CFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(("objc_msgSend", objc))

        get_class = objc.objc_getClass
        selector = objc.sel_registerName
        image_class = get_class(b"NSImage")
        icon_name = send_text(
            get_class(b"NSString"),
            selector(b"stringWithUTF8String:"),
            b"NSApplicationIcon",
        )
        existing = send_id_arg(
            image_class,
            selector(b"imageNamed:"),
            icon_name,
        )
        if existing:
            send_bool_arg(existing, selector(b"setName:"), None)

        ns_path = send_text(
            get_class(b"NSString"),
            selector(b"stringWithUTF8String:"),
            str(icon_path).encode("utf-8"),
        )
        image = send_id_arg(
            send_id(image_class, selector(b"alloc")),
            selector(b"initWithContentsOfFile:"),
            ns_path,
        )
        application = send_id(
            get_class(b"NSApplication"),
            selector(b"sharedApplication"),
        )
        if not image or not application:
            return False
        named = send_bool_arg(image, selector(b"setName:"), icon_name)
        send_void_arg(
            application,
            selector(b"setApplicationIconImage:"),
            image,
        )
        send_void(image, selector(b"release"))
        return bool(named)
    except (AttributeError, OSError, TypeError, ValueError):
        return False
