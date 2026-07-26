"""Modern modal dialogs used by the GUI."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox

import customtkinter as ctk

from timelapse_manager.presets import PRESET_DESCRIPTIONS
from timelapse_manager.ui.theme import (
    ACCENT,
    BACKGROUND,
    BORDER,
    FONT_FAMILY,
    MONOSPACE_FONT_FAMILY,
    MUTED,
    SURFACE,
    SURFACE_ALT,
    TEXT,
)
from timelapse_manager.ui.widgets import action_button


def _center_on_parent(
    window: ctk.CTkToplevel,
    parent: tk.Misc,
    width: int,
    height: int,
) -> None:
    parent.update_idletasks()
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


class YamlEditorDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        load_text: Callable[[], str],
        save_text: Callable[[str], object],
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.minsize(620, 480)
        self.configure(fg_color=BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.load_text = load_text
        self.save_text = save_text
        self.on_saved = on_saved
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        _center_on_parent(self, parent, 820, 700)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 12))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text=title,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=21, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="修改任务级参数，保存前会自动校验 YAML。",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        editor_frame = ctk.CTkFrame(
            self,
            fg_color=SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        editor_frame.grid(row=1, column=0, sticky="nsew", padx=24)
        editor_frame.grid_rowconfigure(0, weight=1)
        editor_frame.grid_columnconfigure(0, weight=1)
        self.text = ctk.CTkTextbox(
            editor_frame,
            wrap="none",
            corner_radius=12,
            border_width=0,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            font=ctk.CTkFont(family=MONOSPACE_FONT_FAMILY, size=12),
            undo=True,
        )
        self.text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=24, pady=18)
        buttons.grid_columnconfigure(1, weight=1)
        action_button(buttons, "重新读取", self.reload, width=100).grid(
            row=0, column=0, sticky="w"
        )
        action_button(buttons, "关闭", self.destroy, width=88).grid(
            row=0, column=2, padx=(8, 0)
        )
        ctk.CTkButton(
            buttons,
            text="校验并保存",
            command=self.save,
            width=124,
            fg_color=ACCENT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).grid(row=0, column=3, padx=(8, 0))

        self.bind("<Control-s>", lambda _event: self.save())
        self.bind("<Command-s>", lambda _event: self.save())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.reload()
        self.after(80, self._activate)

    def _activate(self) -> None:
        self.lift()
        self.focus_force()
        self.grab_set()

    def reload(self) -> None:
        try:
            value = self.load_text()
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc), parent=self)
            return
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", value)

    def save(self) -> None:
        try:
            self.save_text(self.text.get("1.0", "end-1c"))
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        if self.on_saved:
            self.on_saved()
        messagebox.showinfo("保存成功", "YAML 已校验并保存。", parent=self)


class NewTaskDialog(ctk.CTkToplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("新建任务")
        self.resizable(False, False)
        self.configure(fg_color=BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.result: tuple[str, str] | None = None
        self.name_value = tk.StringVar(value="延时摄影任务")
        self.preset_value = tk.StringVar(value="scheduled_once")
        _center_on_parent(self, parent, 540, 450)

        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self,
            text="创建延时摄影任务",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=23, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 4))
        ctk.CTkLabel(
            self,
            text="定时与永续预设会立即启动，Manual 任务会先进入配置编辑。",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 22))

        form = ctk.CTkFrame(
            self,
            fg_color=SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        form.grid(row=2, column=0, sticky="ew", padx=28)
        form.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            form,
            text="任务名称",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 7))
        self.name_entry = ctk.CTkEntry(
            form,
            textvariable=self.name_value,
            height=38,
            corner_radius=9,
            border_color=BORDER,
            fg_color=SURFACE_ALT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        )
        self.name_entry.grid(row=1, column=0, sticky="ew", padx=18)
        ctk.CTkLabel(
            form,
            text="任务预设",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            anchor="w",
        ).grid(row=2, column=0, sticky="ew", padx=18, pady=(16, 7))
        ctk.CTkOptionMenu(
            form,
            variable=self.preset_value,
            values=list(PRESET_DESCRIPTIONS),
            command=lambda _value: self._update_description(),
            height=38,
            corner_radius=9,
            fg_color=ACCENT,
            button_color=ACCENT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).grid(row=3, column=0, sticky="ew", padx=18)
        self.description = ctk.CTkLabel(
            form,
            text="",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            wraplength=450,
            justify="left",
            anchor="w",
        )
        self.description.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=18,
            pady=(10, 18),
        )
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="e", padx=28, pady=22)
        action_button(buttons, "取消", self.destroy, width=88).pack(side=tk.LEFT)
        self.submit_button = ctk.CTkButton(
            buttons,
            text="创建并启动",
            command=self._submit,
            width=120,
            fg_color=ACCENT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        )
        self.submit_button.pack(side=tk.LEFT, padx=(10, 0))
        self._update_description()

        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(80, self._activate)

    def _activate(self) -> None:
        self.lift()
        self.name_entry.focus_set()
        self.grab_set()

    def _update_description(self) -> None:
        preset = self.preset_value.get()
        self.description.configure(text=PRESET_DESCRIPTIONS[preset])
        self.submit_button.configure(
            text="创建并编辑" if preset == "manual" else "创建并启动"
        )

    def _submit(self) -> None:
        name = self.name_value.get().strip()
        if not name:
            messagebox.showwarning("名称为空", "请输入任务名称。", parent=self)
            return
        self.result = (name, self.preset_value.get())
        self.destroy()
